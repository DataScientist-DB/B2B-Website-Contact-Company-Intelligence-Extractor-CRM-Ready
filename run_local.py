import json
from src.core import run_core

if __name__ == "__main__":
    input_data = {
        "startUrls": [
            {"url": "https://www.redcross.org"},
            {"url": "https://www.habitat.org"},

        ],
        "maxPagesPerSite": 1,
        "extractSocialLinks": False,
    }

    results = run_core(input_data)
    print(json.dumps(results, indent=2, ensure_ascii=False))
