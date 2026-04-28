from pdca.observability.redaction import redact, redact_dict_keys, safe_redact


def test_aws_access_key_is_always_redacted():
    value = "token AKIAIOSFODNN7EXAMPLE end"

    assert "AKIAIOSFODNN7EXAMPLE" not in redact(value, mode="off")
    assert "<REDACTED-CREDENTIAL>" in redact(value, mode="off")


def test_aws_secret_key_heuristic_is_redacted():
    secret = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"

    assert redact(secret, mode="full") == "<REDACTED-CREDENTIAL>"


def test_arn_account_is_masked_in_full_mode():
    value = "arn:aws:s3:us-east-1:123456789012:bucket/company-data"

    result = redact(value, mode="full")

    assert "123456789012" not in result
    assert "***9012" in result


def test_internal_mode_keeps_arn_account_but_redacts_credentials():
    value = "arn:aws:iam::123456789012:role/Admin AKIAIOSFODNN7EXAMPLE"

    result = redact(value, mode="internal")

    assert "123456789012" in result
    assert "AKIAIOSFODNN7EXAMPLE" not in result


def test_nested_dict_and_lists_are_redacted_recursively():
    value = {
        "tool_params": {
            "bucket": "company-prod-data",
            "target": "arn:aws:s3:ap-southeast-1:123456789012:bucket/company-prod-data",
        },
        "findings": [
            {"resource": "s3://company-prod-data"},
            {"account_id": "123456789012"},
        ],
    }

    result = redact(value, mode="full")
    text = str(result)

    assert "company-prod-data" not in text
    assert "123456789012" not in text
    assert "bkt-" in text


def test_mode_off_keeps_non_secret_identity_data():
    value = "arn:aws:s3:us-east-1:123456789012:bucket/company-prod-data"

    assert redact(value, mode="off") == value


def test_sensitive_dict_keys_are_stripped_before_recurse():
    value = {"aws_access_key_id": "AKIAIOSFODNN7EXAMPLE", "name": "ok"}

    result = redact_dict_keys(value)

    assert result["aws_access_key_id"] == "<REDACTED-CREDENTIAL>"
    assert result["name"] == "ok"


def test_safe_redact_catches_circular_reference():
    value = {}
    value["self"] = value

    assert safe_redact(value) == "<redaction-error>"


def test_12_digit_false_positive_is_accepted_and_documented():
    assert redact("timestamp 202604271234", mode="full") == "timestamp ***1234"


def test_uuid_run_id_is_not_treated_as_bucket_name():
    run_id = "12345678-1234-4abc-9def-1234567890ab"

    assert redact(run_id, mode="full") == run_id
