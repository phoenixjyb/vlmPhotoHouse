import logging, json, sys, time, traceback
from datetime import datetime, timezone
from typing import Any, Dict
from .config import get_settings

settings = get_settings()

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base: Dict[str, Any] = {
            'ts': datetime.utcnow().isoformat() + 'Z',
            'level': record.levelname,
            'msg': record.getMessage(),
            'logger': record.name,
        }
        for attr in ('request_id','path','method','status','duration_ms','task_id','task_type','exc_type'):
            v = getattr(record, attr, None)
            if v is not None:
                base[attr] = v
        if record.exc_info:
            base['trace'] = self.formatException(record.exc_info)
        return json.dumps(base, ensure_ascii=False)

def configure_logging():
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    handler = logging.StreamHandler(sys.stdout)
    if settings.log_format == 'json':
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s')
    handler.setFormatter(formatter)
    root.addHandler(handler)
    root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    # Reduce noisy libs
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
    logging.getLogger('alembic').setLevel(logging.WARNING)

# Delay automatic configuration to when explicitly invoked
if __name__ == 'app.logging':
    try:
        configure_logging()
    except Exception:
        pass
