"""Score core.py against both answer keys. Usage: python eval.py"""

import json
import pathlib
from concurrent.futures import ThreadPoolExecutor

import core

ROOT = pathlib.Path(__file__).parent
DATA = ROOT / "data"
FIXTURES = ROOT / "fixtures"
SAMPLES = [("credit_report.pdf", "ground_truth.json"),
           ("credit_report_tu_style.pdf", "ground_truth_tu_style.json")]


def gt_last4(acct):
    return acct.get("account_last4") or acct["account_number"][-4:]


def expected_predictions(acct):
    if "acceptable_predictions" in acct:
        return acct["acceptable_predictions"]
    return ["likely_coerced"] if acct["label"] == "coerced" else ["likely_hers"]


def score(accounts, key):
    results = []

    def check(name, ok, detail=""):
        results.append(ok)
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail and not ok else ""))

    got = {a["last4"]: a for a in accounts}
    gt = {gt_last4(a): a for a in key["accounts"]}

    found = [l4 for l4 in gt if l4 in got]
    check(f"accounts found {len(found)}/{len(gt)}", len(found) == len(gt),
          f"missing {sorted(set(gt) - set(got))}, extra {sorted(set(got) - set(gt))}")

    for l4, g in gt.items():
        a = got.get(l4)
        if a is None:
            continue
        name = f"{l4} {g['creditor'][:22]}"
        check(f"{name}: balance", a["balance"] == g["balance"], f"got {a['balance']}, want {g['balance']}")
        if g["date_opened"]:
            got_month = (a["date_opened"] or "")[:7]
            check(f"{name}: date_opened", got_month == g["date_opened"][:7],
                  f"got {a['date_opened']}, want {g['date_opened']}")
        want = expected_predictions(g)
        check(f"{name}: prediction", a["prediction"] in want, f"got {a['prediction']}, want {want}")

    if "4471" in got:
        check("4471 Fresno CU never likely_coerced", got["4471"]["prediction"] != "likely_coerced",
              f"got {got['4471']['prediction']}")
    link_ok = (got.get("3391", {}).get("linked_last4") == "8820"
               and got.get("8820", {}).get("linked_last4") == "3391")
    check("link 3391 <-> 8820", link_ok,
          f"3391->{got.get('3391', {}).get('linked_last4')}, 8820->{got.get('8820', {}).get('linked_last4')}")
    return results


def run_sample(sample):
    pdf_name, key_name = sample
    return core.analyze((DATA / pdf_name).read_bytes(), json.loads((DATA / "dana_intake.json").read_text()))


def main():
    with ThreadPoolExecutor(max_workers=len(SAMPLES)) as pool:
        responses = list(pool.map(run_sample, SAMPLES))

    total_pass = total = 0
    all_passed = True
    for (pdf_name, key_name), accounts in zip(SAMPLES, responses):
        key = json.loads((DATA / key_name).read_text())
        print(f"\n{pdf_name}  vs  {key_name}")
        results = score(accounts, key)
        print(f"  -> {sum(results)}/{len(results)}")
        total_pass += sum(results)
        total += len(results)
        all_passed &= all(results)

    print(f"\nTOTAL {total_pass}/{total}")
    if all_passed:
        FIXTURES.mkdir(exist_ok=True)
        for (pdf_name, _), accounts in zip(SAMPLES, responses):
            out = FIXTURES / (pdf_name.removesuffix(".pdf") + ".json")
            out.write_text(json.dumps(accounts, indent=2))
            print(f"saved {out.relative_to(ROOT)}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
