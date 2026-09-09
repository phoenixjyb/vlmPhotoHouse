"""Read-only offline provisioning plans. No apply path or HTTP registration.

The local caller already has direct database authority. A plan is a review artifact,
not a session or access grant. Future application must revalidate under its own
write transaction and separately establish the reviewed operator/target authority.
"""
import hashlib
import hmac
import json
import re
import uuid

from .credentials import phone_login
from .service import AccessService

MAX_ASSETS = 10000
LIFETIME = 900


class PlanRejected(ValueError):
    """Generic refusal that does not echo database contents or credentials."""


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()


def _library(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{2,63}', value):
        raise PlanRejected('Choose an explicit portable library ID')
    return value


class ProvisioningPlanner:
    def __init__(self, connection, *, clock):
        self.access = AccessService(connection, clock=clock)
        if connection.execute('PRAGMA query_only').fetchone()[0] != 1:
            raise PlanRejected('Planning requires a read-only connection')

    def _mac(self, purpose, value):
        row = self.access.db.execute('SELECT secret FROM access_admission_key WHERE id=1').fetchone()
        if not row or not isinstance(row[0], bytes) or len(row[0]) != 32:
            raise PlanRejected('Planning unavailable')
        return hmac.new(row[0], b'PhotoHouse offline plan v1\0' + purpose.encode() + b'\0' + _json(value), hashlib.sha256).hexdigest()

    def _state(self, operation, target):
        db = self.access.db
        if operation == 'bootstrap_owner':
            if set(target) != {'phone_login','library_id'}:
                raise PlanRejected('Invalid plan')
            library = _library(target['library_id'])
            if phone_login(target['phone_login']) != target['phone_login']:
                raise PlanRejected('Invalid plan')
            if db.execute('SELECT id FROM access_accounts WHERE phone_login=?', (target['phone_login'],)).fetchone() or db.execute(
                    'SELECT id FROM access_libraries WHERE id=?', (library,)).fetchone():
                raise PlanRejected('Owner or library already exists')
            return {'new_owner':True,'new_operator':True,'new_library':True,
                    'originals_granted':False,'legacy_assets_assigned':0}
        if operation != 'assign_unmapped_assets' or set(target) != {'library_id','operator_account_id','asset_ids'}:
            raise PlanRejected('Invalid plan')
        library = _library(target['library_id'])
        actor = target['operator_account_id']
        if not isinstance(actor, str) or len(actor) != 36:
            raise PlanRejected('Explicit operator account required')
        row = db.execute('''SELECT m.revision FROM access_memberships m
            JOIN access_accounts a ON a.id=m.account_id JOIN access_libraries l ON l.id=m.library_id
            JOIN access_operators o ON o.account_id=m.account_id
            WHERE m.account_id=? AND m.library_id=? AND m.role='owner' AND m.status='approved'
            AND a.state='active' AND l.state='active' AND (m.expires_at IS NULL OR m.expires_at>?)''',
            (actor,library,self.access._now())).fetchone()
        if not row:
            raise PlanRejected('Selected operator and library owner required')
        raw_ids = target['asset_ids']
        if not isinstance(raw_ids,list) or not 1 <= len(raw_ids) <= MAX_ASSETS:
            raise PlanRejected('Select a bounded nonempty asset list')
        if any(not isinstance(item,str) or not re.fullmatch(r'[1-9][0-9]{0,18}',item) or int(item)>2**63-1 for item in raw_ids):
            raise PlanRejected('Invalid asset selection')
        ids = [int(item) for item in raw_ids]
        if ids != sorted(set(ids)):
            raise PlanRejected('Asset selection must be sorted and unique')
        fingerprints=[]
        for start in range(0,len(ids),500):
            chunk=ids[start:start+500]
            rows=db.execute('''SELECT a.id,a.path,a.hash_sha256,a.status,m.library_id FROM assets a
                LEFT JOIN access_asset_libraries m ON m.asset_id=a.id WHERE a.id IN ('''+','.join('?' for _ in chunk)+') ORDER BY a.id', chunk).fetchall()
            if len(rows)!=len(chunk) or any(item[3] not in (None,'active') or item[4] is not None for item in rows):
                raise PlanRejected('Only existing active unmapped assets can be planned')
            fingerprints.extend(list(item) for item in rows)
        audience=db.execute('''SELECT m.account_id,m.status,m.role,m.revision,m.expires_at,m.originals,a.state
            FROM access_memberships m JOIN access_accounts a ON a.id=m.account_id
            WHERE m.library_id=? ORDER BY m.account_id''', (library,)).fetchall()
        current=[member for member in audience if member[1]=='approved' and member[6]=='active'
                 and (member[4] is None or member[4]>self.access._now())]
        return {'operator_revision':str(row[0]),'asset_state':self._mac('asset-state',fingerprints),'count':len(ids),
                'audience_state':self._mac('library-audience',audience), 'current_readers':len(current),
                'current_original_readers':sum(bool(member[5]) for member in current),
                'originals_granted':False,'moves_or_media_writes':False}

    def _plan(self, operation, target):
        with self.access._transaction():
            now=self.access._now()
            payload={'version':1,'operation':operation,'plan_id':str(uuid.uuid4()),
                     'created_at':now,'expires_at':now+LIFETIME,'target':target,
                     'database_binding':self._mac('database-binding',1),
                     'expected':self._state(operation,target)}
            return {'plan':payload,'seal':self._mac('sealed-review',payload)}

    def owner(self, *, phone, library_id):
        return self._plan('bootstrap_owner',{'phone_login':phone_login(phone),'library_id':_library(library_id)})

    def assets(self, *, library_id, operator_account_id, asset_ids):
        if not isinstance(asset_ids,list) or not 1 <= len(asset_ids) <= MAX_ASSETS or any(type(item) is not int for item in asset_ids):
            raise PlanRejected('Explicit integer asset IDs required')
        if len(asset_ids)!=len(set(asset_ids)):
            raise PlanRejected('Duplicate asset selection')
        return self._plan('assign_unmapped_assets',{'library_id':_library(library_id),
            'operator_account_id':operator_account_id,'asset_ids':[str(item) for item in sorted(asset_ids)]})

    def validate(self, envelope):
        """Read-only freshness/integrity check; success grants no apply authority."""
        try:
            if not isinstance(envelope,dict) or set(envelope)!={'plan','seal'} or len(_json(envelope))>2_000_000:
                raise PlanRejected('Invalid plan')
            plan,seal=envelope['plan'],envelope['seal']
            if not isinstance(plan,dict) or set(plan)!={'version','operation','plan_id','created_at','expires_at','target','database_binding','expected'}:
                raise PlanRejected('Invalid plan')
            if not isinstance(seal,str) or not re.fullmatch('[0-9a-f]{64}',seal):
                raise PlanRejected('Invalid plan')
            with self.access._transaction():
                now=self.access._now()
                if (plan['version']!=1 or type(plan['created_at']) is not int or type(plan['expires_at']) is not int
                        or not plan['created_at']<=now<plan['expires_at'] or plan['expires_at']-plan['created_at']!=LIFETIME
                        or not hmac.compare_digest(seal,self._mac('sealed-review',plan))
                        or plan['database_binding']!=self._mac('database-binding',1)):
                    raise PlanRejected('Invalid or expired plan')
                if plan['expected']!=self._state(plan['operation'],plan['target']):
                    raise PlanRejected('Plan state changed; review again')
            return {'valid':True,'operation':plan['operation'],'plan_id':plan['plan_id'],'applied':False}
        except PlanRejected:
            raise
        except (KeyError,TypeError,ValueError,OverflowError,RecursionError,UnicodeError):
            raise PlanRejected('Invalid plan') from None
