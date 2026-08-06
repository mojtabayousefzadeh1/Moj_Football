import requests
import json
from datetime import datetime


URL = "https://sportscore.com/api/widget/matches/?sport=football"


def main():

    try:
        response = requests.get(URL, timeout=30)

        print("Status Code:", response.status_code)

        data = response.json()

        print("\n===== RAW DATA =====\n")

        print(json.dumps(
            data,
            indent=2,
            ensure_ascii=False
        )[:5000])


        filename = "sportscore_response.json"

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(
                data,
                f,
                indent=2,
                ensure_ascii=False
            )

        print("\nذخیره شد:", filename)


    except Exception as e:
        print("ERROR:", e)


if __name__ == "__main__":
    main()
