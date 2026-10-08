from hashlib import sha256


def execute_plan(plan, plan_id: str, write_gateway) -> list[dict]:
    results = []
    return_id = None
    for i, action in enumerate(plan.actions):
        args = dict(action.args)
        args = {k: (return_id if v == "$return_id" else v) for k, v in args.items()}
        key = sha256(f"{plan_id}:{i}".encode()).hexdigest()
        name = action.tool.value
        result = getattr(write_gateway, name)(**args, idempotency_key=key)
        results.append({"tool": name, "result": result})
        if not result.get("ok"):
            break
        if name == "create_return":
            return_id = result["return_id"]
    return results
