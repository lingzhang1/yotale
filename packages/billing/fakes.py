"""In-memory DynamoDB double that EVALUATES real expression semantics (tests only).

Unlike the older user_quota fake (which pattern-matches the exact expression strings the quota module emits),
this one parses and evaluates UpdateExpression (SET / ADD / REMOVE, if_not_exists) and ConditionExpression /
FilterExpression (AND / OR / NOT, parentheses, comparisons, attribute_exists, attribute_not_exists, begins_with),
so a billing test fails when an expression would fail on real DynamoDB. It also rejects arithmetic inside a
condition (`+`/`-`), which DynamoDB rejects with a ValidationException.

Models: get_item, update_item (upsert, like DynamoDB), query (begins_with sort key + filter), and
transact_write_items (all-or-nothing, with per-leg CancellationReasons). Single table keyed by
(story_user_id, quota_period), matching the shared UserUsage table.
"""
from __future__ import annotations

import copy
import re
import threading

_TOKEN = re.compile(r"\s*(<>|<=|>=|=|<|>|\(|\)|,|[#:]?[A-Za-z_][A-Za-z0-9_.]*|\+|-)")


class FakeClientError(Exception):
    """Mimics botocore.exceptions.ClientError closely enough for the ledger's error classification."""

    def __init__(self, code: str, reasons: list[str] | None = None):
        super().__init__(code)
        self.response = {"Error": {"Code": code}}
        if reasons is not None:
            self.response["CancellationReasons"] = [{"Code": r} for r in reasons]
        self.__class__ = type(code, (FakeClientError,), {})  # so type(e).__name__ == code, like botocore


def _tokens(expr: str) -> list[str]:
    out, pos = [], 0
    expr = expr.strip()
    while pos < len(expr):
        m = _TOKEN.match(expr, pos)
        if not m:
            raise ValueError(f"unparseable expression near: {expr[pos:pos + 20]!r}")
        out.append(m.group(1))
        pos = m.end()
    return out


class _Ctx:
    def __init__(self, item: dict, names: dict, values: dict):
        self.item, self.names, self.values = item, names, values

    def attr(self, tok: str):
        name = self.names[tok] if tok.startswith("#") else tok
        return self.item.get(name)

    def value(self, tok: str):
        if tok.startswith(":"):
            return self.values[tok]
        return self.attr(tok)


def _cmp_val(v):
    if v is None:
        return None
    if "N" in v:
        return float(v["N"])
    if "S" in v:
        return v["S"]
    if "BOOL" in v:
        return v["BOOL"]
    return None


class _CondParser:
    def __init__(self, expr: str, ctx: _Ctx):
        if "+" in expr or re.search(r"\s-\s", expr):
            raise ValueError("Invalid ConditionExpression: arithmetic is not allowed in a condition "
                             "(DynamoDB ValidationException)")
        self.t, self.i, self.ctx = _tokens(expr), 0, ctx

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else None

    def eat(self, tok=None):
        cur = self.peek()
        if tok is not None and cur != tok:
            raise ValueError(f"expected {tok!r}, got {cur!r}")
        self.i += 1
        return cur

    def parse(self) -> bool:
        v = self.or_()
        if self.peek() is not None:
            raise ValueError(f"trailing tokens: {self.t[self.i:]}")
        return v

    def or_(self) -> bool:
        v = self.and_()
        while (self.peek() or "").upper() == "OR":
            self.eat()
            r = self.and_()
            v = v or r
        return v

    def and_(self) -> bool:
        v = self.not_()
        while (self.peek() or "").upper() == "AND":
            self.eat()
            r = self.not_()
            v = v and r
        return v

    def not_(self) -> bool:
        if (self.peek() or "").upper() == "NOT":
            self.eat()
            return not self.not_()
        return self.atom()

    def atom(self) -> bool:
        tok = self.peek()
        if tok == "(":
            self.eat("(")
            v = self.or_()
            self.eat(")")
            return v
        if tok in ("attribute_exists", "attribute_not_exists", "begins_with"):
            fn = self.eat()
            self.eat("(")
            a = self.eat()
            arg = None
            if fn == "begins_with":
                self.eat(",")
                arg = self.eat()
            self.eat(")")
            cur = self.ctx.attr(a)
            if fn == "attribute_exists":
                return cur is not None
            if fn == "attribute_not_exists":
                return cur is None
            return cur is not None and str(_cmp_val(cur)).startswith(str(_cmp_val(self.ctx.value(arg))))
        left = self.ctx.value(self.eat())
        op = self.eat()
        right = self.ctx.value(self.eat())
        lv, rv = _cmp_val(left), _cmp_val(right)
        if lv is None or rv is None:
            return op == "<>" and lv != rv   # comparisons with a missing attribute are false (except <>)
        return {"=": lv == rv, "<>": lv != rv, "<": lv < rv, "<=": lv <= rv, ">": lv > rv, ">=": lv >= rv}[op]


def evaluate_condition(expr: str | None, item: dict, names: dict, values: dict) -> bool:
    if not expr:
        return True
    return _CondParser(expr, _Ctx(item, names, values)).parse()


def _split_clauses(ue: str) -> dict[str, str]:
    parts = re.split(r"\b(SET|ADD|REMOVE|DELETE)\b", ue)
    out: dict[str, str] = {}
    for i in range(1, len(parts), 2):
        out[parts[i]] = parts[i + 1].strip()
    return out


def _split_top(s: str) -> list[str]:
    out, depth, cur = [], 0, ""
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur.strip()); cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def apply_update(item: dict, ue: str, names: dict, values: dict) -> None:
    ctx = _Ctx(item, names, values)
    name_of = lambda t: names[t] if t.startswith("#") else t  # noqa: E731
    for kind, body in _split_clauses(ue).items():
        for part in _split_top(body):
            if kind == "SET":
                lhs, rhs = [x.strip() for x in part.split("=", 1)]
                m = re.fullmatch(r"if_not_exists\(\s*([#\w.]+)\s*,\s*(:\w+)\s*\)", rhs)
                if m:
                    if ctx.attr(m.group(1)) is None:
                        item[name_of(lhs)] = copy.deepcopy(values[m.group(2)])
                else:
                    if "+" in rhs or re.search(r"\s-\s", rhs):
                        raise ValueError("fake: arithmetic in SET is not modelled; use ADD")
                    item[name_of(lhs)] = copy.deepcopy(ctx.value(rhs))
            elif kind == "ADD":
                a, v = part.split()
                cur = float(item.get(name_of(a), {"N": "0"})["N"])
                new = cur + float(values[v]["N"])
                item[name_of(a)] = {"N": str(int(new)) if new == int(new) else str(new)}
            elif kind == "REMOVE":
                item.pop(name_of(part.strip()), None)


class FakeDDB:
    def __init__(self):
        self.items: dict[tuple, dict] = {}
        self.lock = threading.RLock()
        self.writes = 0

    @staticmethod
    def _k(Key):
        return (Key["story_user_id"]["S"], Key["quota_period"]["S"])

    def get_item(self, TableName, Key, ConsistentRead=False):
        with self.lock:
            it = self.items.get(self._k(Key))
            return {"Item": copy.deepcopy(it)} if it else {}

    def _update_locked(self, Key, UpdateExpression, ConditionExpression=None,
                       ExpressionAttributeNames=None, ExpressionAttributeValues=None):
        names, values = ExpressionAttributeNames or {}, ExpressionAttributeValues or {}
        text = f"{UpdateExpression} {ConditionExpression or ''}"
        for ph in values:                      # real DynamoDB rejects unused ExpressionAttributeValues
            if ph not in text:
                raise ValueError(f"ValidationException: unused expression attribute value {ph}")
        k = self._k(Key)
        existing = self.items.get(k)
        # DynamoDB evaluates the condition against the stored item (an absent item has NO attributes,
        # including its key attributes: attribute_not_exists(story_user_id) is the create-only idiom).
        cond_item = existing if existing is not None else {}
        if not evaluate_condition(ConditionExpression, cond_item, names, values):
            raise FakeClientError("ConditionalCheckFailedException")
        item = copy.deepcopy(existing) if existing is not None else {
            "story_user_id": Key["story_user_id"], "quota_period": Key["quota_period"]}
        apply_update(item, UpdateExpression, names, values)
        self.items[k] = item
        self.writes += 1

    def update_item(self, TableName, Key, UpdateExpression, ConditionExpression=None,
                    ExpressionAttributeNames=None, ExpressionAttributeValues=None):
        with self.lock:
            self._update_locked(Key, UpdateExpression, ConditionExpression,
                                ExpressionAttributeNames, ExpressionAttributeValues)

    def query(self, TableName, KeyConditionExpression, ExpressionAttributeValues,
              FilterExpression=None, ExpressionAttributeNames=None, Limit=None, **_):
        names, values = ExpressionAttributeNames or {}, ExpressionAttributeValues or {}
        pk = values[":pk"]["S"]
        prefix = values[":sk"]["S"]
        out = []
        with self.lock:
            for (p, sk), it in sorted(self.items.items()):
                if p == pk and sk.startswith(prefix) and evaluate_condition(FilterExpression, it, names, values):
                    out.append(copy.deepcopy(it))
                    if Limit and len(out) >= Limit:
                        break
        return {"Items": out}

    def transact_write_items(self, TransactItems):
        with self.lock:
            snapshot = copy.deepcopy(self.items)
            reasons = ["None"] * len(TransactItems)
            try:
                for i, ti in enumerate(TransactItems):
                    leg = ti.get("Update") or ti.get("ConditionCheck")
                    try:
                        if "Update" in ti:
                            self._update_locked(leg["Key"], leg["UpdateExpression"], leg.get("ConditionExpression"),
                                                leg.get("ExpressionAttributeNames"), leg.get("ExpressionAttributeValues"))
                        else:
                            it = self.items.get(self._k(leg["Key"]), {})
                            if not evaluate_condition(leg.get("ConditionExpression"), it,
                                                      leg.get("ExpressionAttributeNames") or {},
                                                      leg.get("ExpressionAttributeValues") or {}):
                                raise FakeClientError("ConditionalCheckFailedException")
                    except FakeClientError:
                        reasons[i] = "ConditionalCheckFailed"
                        raise
            except FakeClientError:
                self.items = snapshot
                raise FakeClientError("TransactionCanceledException", reasons)
