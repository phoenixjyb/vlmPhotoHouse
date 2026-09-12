"""Validate actual synthetic producer output and strict candidate schema negatives.

Test-only dependency: jsonschema==4.25.1. No live runtime or index is consulted.
"""
import copy
import json
from pathlib import Path
import sys
from jsonschema import Draft202012Validator
from build_phone_discovery_http_fixture import build

ROOT=Path(__file__).resolve().parents[1]


def main():
    schema=json.loads((ROOT/'docs/security/phone-discovery-http-candidate-schema.json').read_text())
    expected=json.loads((ROOT/'docs/security/phone-discovery-http-candidate-examples.json').read_text())
    actual=build();assert actual==expected,'Producer fixture drift requires contract review'
    Draft202012Validator.check_schema(schema)
    validator=Draft202012Validator(schema)
    for example in actual['examples']:validator.validate(example['body'])
    identifier=Draft202012Validator(dict(schema,oneOf=[{'$ref':'#/$defs/id'}]))
    for value in ('1','9007199254740993','9223372036854775807'):identifier.validate(value)
    for value in (1,True,'0','01','-1','9223372036854775808','9999999999999999999'):
        assert not identifier.is_valid(value),value
    search=copy.deepcopy(next(e['body'] for e in actual['examples'] if e['name']=='all-media-first'))
    bad=[]
    bad.append(dict(search,unexpected='private'))
    bad.append(dict(search,page=True))
    bad.append(dict(search,binding='not-a-binding'))
    changed=copy.deepcopy(search);changed['items'][0]['id']=9223372036854775807;bad.append(changed)
    changed=copy.deepcopy(search);changed['items'][0]['path']='private';bad.append(changed)
    for value in bad:assert not validator.is_valid(value)
    print(json.dumps({'synthetic_examples':len(actual['examples']),'producer_exact_match':True,'valid_id_boundaries':3,'invalid_id_boundaries':7,'invalid_response_cases':len(bad)}))


if __name__=='__main__':main()
