import argparse
import base64
import datetime as dt
import json
import os
from urllib import request


LOCATION_PRESETS = {
    "kingsville": {
        "location_guid": "7b6ea663-6c82-4a7d-b305-ea7d1512a8ff",
        "output_dir": r"C:\Users\arnol\OneDrive\Desktop\AIO-Python\Kingsville Product mixes",
    },
    "alice": {
        "location_guid": "5cb447d0-4b1c-4823-8969-42c437042931",
        "output_dir": r"C:\Users\arnol\OneDrive\Desktop\AIO-Python\Alice Product mixes",
    },
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Toast Product Mix helper with Kingsville/Alice presets."
    )
    parser.add_argument(
        "--mode",
        choices=["decode", "download"],
        default="decode",
        help="decode: save files from a captured Playwright result file; download: call Toast API directly",
    )
    parser.add_argument(
        "--location",
        choices=sorted(LOCATION_PRESETS.keys()),
        required=True,
        help="Location preset",
    )

    # Decode mode args
    parser.add_argument(
        "--json-path",
        help="Path to captured tool result file that starts with 'Result: ...'",
    )

    # Download mode args
    parser.add_argument("--start-date", help="YYYY-MM-DD")
    parser.add_argument("--end-date", help="YYYY-MM-DD")
    parser.add_argument(
        "--authorization",
        help="Authorization header value, usually 'Bearer <token>'",
    )
    parser.add_argument("--management-set-guid", help="toast-management-set-guid")
    parser.add_argument("--restaurant-set-guid", help="toast-restaurant-set-guid")
    parser.add_argument(
        "--restaurant-external-id",
        help="toast-restaurant-external-id (defaults to location GUID)",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip dates where output file already exists",
    )
    return parser.parse_args()


def normalize_result_blob(raw_text):
    raw = raw_text.strip()
    if raw.startswith('Result: "'):
        raw = raw[9:]
    if raw.endswith('"'):
        raw = raw[:-1]
    return raw.replace('\\"', '"').replace('\\\\', '\\')


def ensure_output_dir(path):
    os.makedirs(path, exist_ok=True)


def date_iter(start_date, end_date):
    current = start_date
    while current <= end_date:
        yield current
        current += dt.timedelta(days=1)


def product_mix_filename(day):
    d = day.strftime("%Y-%m-%d")
    return f"ProductMix_{d}_{d}.xlsx"


def save_decoded_files(json_path, out_dir):
    with open(json_path, "r", encoding="utf-8") as file_obj:
        raw = file_obj.read()

    items = json.loads(normalize_result_blob(raw))
    saved = 0
    for item in items:
        if item.get("error"):
            print(f"ERROR {item['date']}: {item['error']}")
            continue
        day = dt.datetime.strptime(item["date"], "%Y%m%d").date()
        filename = product_mix_filename(day)
        file_path = os.path.join(out_dir, filename)
        data = base64.b64decode(item["b64"])
        with open(file_path, "wb") as file_obj:
            file_obj.write(data)
        print(f"Saved {filename} ({len(data)} bytes)")
        saved += 1

    print(f"Done! Saved {saved} files to {out_dir}")


def make_headers(args, location_guid):
    restaurant_external_id = args.restaurant_external_id or location_guid
    return {
        "Authorization": args.authorization,
        "Content-Type": "application/json",
        "toast-management-set-guid": args.management_set_guid,
        "toast-restaurant-external-id": restaurant_external_id,
        "toast-restaurant-set-guid": args.restaurant_set_guid,
    }


def make_body(location_guid, yyyymmdd):
    return {
        "reportName": "productMix/MenuBreakdownComparison",
        "locations": [[{"locationGuid": location_guid, "locationType": "RESTAURANT"}]],
        "dateRanges": {
            "customDateRanges": [
                {"startDateYYYYMMDD": yyyymmdd, "endDateYYYYMMDD": yyyymmdd}
            ]
        },
        "parameters": {
            "excludeModifiers": True,
            "selectedColumns": [
                "tagNames",
                "quantitySold",
                "avgPrice",
                "itemCOGS",
                "grossSale",
                "discountAmount",
                "refundAmount",
                "netSale",
                "netCOGS",
                "grossProfitValue",
                "grossProfitAsPercentageOfNetSales",
                "taxAmount",
                "voidedAmount",
                "wastedCount",
                "wastedAmount",
            ],
            "selectedLevels": [
                "menus",
                "menuGroups",
                "subgroups",
                "menuItems",
                "openItems",
            ],
        },
        "renderer": "EXCEL",
        "dispatcher": {"type": "LIVE"},
    }


def http_post_json(url, headers, payload):
    req = request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with request.urlopen(req, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def http_get_bytes(url, headers):
    req = request.Request(url, headers=headers, method="GET")
    with request.urlopen(req, timeout=60) as response:
        return response.read()


def download_files(args, location_guid, out_dir):
    if not (args.start_date and args.end_date):
        raise ValueError("--start-date and --end-date are required for --mode download")
    if not (args.authorization and args.management_set_guid and args.restaurant_set_guid):
        raise ValueError(
            "--authorization, --management-set-guid, and --restaurant-set-guid are required for --mode download"
        )

    start_date = dt.datetime.strptime(args.start_date, "%Y-%m-%d").date()
    end_date = dt.datetime.strptime(args.end_date, "%Y-%m-%d").date()
    headers = make_headers(args, location_guid)

    saved = 0
    skipped = 0
    failed = 0

    for day in date_iter(start_date, end_date):
        yyyymmdd = day.strftime("%Y%m%d")
        filename = product_mix_filename(day)
        file_path = os.path.join(out_dir, filename)

        if args.skip_existing and os.path.exists(file_path):
            print(f"Skipped {filename} (exists)")
            skipped += 1
            continue

        try:
            body = make_body(location_guid, yyyymmdd)
            resp = http_post_json(
                "https://www.toasttab.com/api/service/report-generator/v1/reportRequest",
                headers,
                body,
            )
            guid = resp["reportRequestGuid"]
            file_bytes = http_get_bytes(
                f"https://www.toasttab.com/api/service/report-generator/v1/reportRequest/{guid}/results",
                headers,
            )
            with open(file_path, "wb") as file_obj:
                file_obj.write(file_bytes)
            print(f"Saved {filename} ({len(file_bytes)} bytes)")
            saved += 1
        except Exception as exc:  # pylint: disable=broad-except
            print(f"ERROR {filename}: {exc}")
            failed += 1

    print(f"Done! saved={saved}, skipped={skipped}, failed={failed}")


def main():
    args = parse_args()
    preset = LOCATION_PRESETS[args.location]
    location_guid = preset["location_guid"]
    out_dir = preset["output_dir"]
    ensure_output_dir(out_dir)

    if args.mode == "decode":
        if not args.json_path:
            raise ValueError("--json-path is required for --mode decode")
        save_decoded_files(args.json_path, out_dir)
    else:
        download_files(args, location_guid, out_dir)


if __name__ == "__main__":
    main()
