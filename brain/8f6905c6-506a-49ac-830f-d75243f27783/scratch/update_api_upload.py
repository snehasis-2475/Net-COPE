with open("api/main.py", "r", encoding="utf-8") as f:
    content = f.read()

target = '''    if not file.filename.endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must be a CSV (.csv).",
        )

    content = await file.read()
    df, warnings = load_telemetry_csv(content)'''

replacement = '''    fname = (file.filename or "").lower()
    if not (fname.endswith(".csv") or fname.endswith(".json")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must be a CSV (.csv) or JSON (.json).",
        )

    raw_bytes = await file.read()
    warnings = []
    if fname.endswith(".json"):
        try:
            parsed = json.loads(raw_bytes.decode("utf-8"))
            items = parsed if isinstance(parsed, list) else parsed.get("records", parsed.get("telemetry", [parsed]))
            df, warnings = orchestrator.validate_and_normalize_telemetry(items)
        except Exception as jerr:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Failed to parse JSON file: {str(jerr)}",
            )
    else:
        df, warnings = load_telemetry_csv(raw_bytes)'''

assert target in content, "Target not found in api/main.py"
content = content.replace(target, replacement, 1)

with open("api/main.py", "w", encoding="utf-8") as f:
    f.write(content)

print("api/main.py updated successfully to support both CSV and JSON uploads!")

