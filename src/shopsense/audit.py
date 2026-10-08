import json
from contextlib import closing

from shopsense.db import repository
from shopsense.db.connection import connect


def record(
    db_path,
    run_id,
    customer_id,
    event,
    intent=None,
    decision=None,
    clause_ids=(),
    detail=None,
):
    with closing(connect(db_path)) as conn:
        repository.insert_audit(
            conn,
            run_id,
            customer_id,
            event,
            intent.intent.value if intent else None,
            decision.value if decision else None,
            json.dumps(list(clause_ids)),
            json.dumps(detail or {}),
        )
