# Scope Detection — Phase 1

The report agent used to assume every scan was an S3 scan. `Amazon S3`
and `bucket` were hardcoded in 15 LLM prompts, and the aggregation layer
referred to `total_buckets` / `bucket_list`. Running the pipeline on an
IAM or multi-service scan produced a report that *textually* described
S3. Phase 1 replaced that with `scope_detector` — a single source of
truth for scope terminology.

Source:
[pdca/agents/report_module/scope_detector.py](../pdca/agents/report_module/scope_detector.py).

## 1. Public surface

```python
from pdca.agents.report_module.scope_detector import (
    detect_scope, is_valid_resource,
    SERVICE_DISPLAY, RESOURCE_TERMS, GENERIC_FALLBACK,
)
```

### `detect_scope(findings, env=None, services_hint=None) -> dict`

Returns:

```
{
    "primary_service":       str | None,   # None when no one service dominates
    "service_list":          List[str],    # all lower-cased service ids in scope
    "is_multi_service":      bool,
    "service_display":       str,          # "Amazon S3" | "AWS IAM" | "AWS Infrastructure"
    "resource_term":         str,          # "bucket" | "IAM entity" | "resource"
    "resource_term_plural":  str,
    "dominance_ratio":       float,        # share of the primary service (0..1)
    "source":                "hint" | "findings" | "empty",
}
```

## 2. Resolution order

1. **Hint wins when single-service.** If `services_hint == ["iam"]`, scope
   locks to IAM regardless of finding counts — the assessment plan is the
   authoritative scope.
2. **Hint + findings, multi-hint.** Count findings that fall within the
   hinted services. If one service's share exceeds `0.7`, that service is
   the primary; otherwise the scope is multi-service.
3. **No hint — infer from findings.** Count findings per service
   (using `finding.service` or the `check_id` prefix, e.g.
   `s3_bucket_public_access` → `s3`). Same dominance rule as above.
4. **Nothing to work with.** Return
   `_empty_scope()` — primary `None`, generic fallback terms, source
   `"empty"`.

Dominance threshold is `_DOMINANT_THRESHOLD = 0.7`.

## 3. `SERVICE_DISPLAY`

Canonical display labels for every AWS service the report agent has
encountered so far:

| Service id       | Display name             |
|------------------|--------------------------|
| s3               | Amazon S3                |
| iam              | AWS IAM                  |
| ec2              | Amazon EC2               |
| rds              | Amazon RDS               |
| lambda           | AWS Lambda               |
| cloudtrail       | AWS CloudTrail           |
| cloudfront       | Amazon CloudFront        |
| kms              | AWS KMS                  |
| sns              | Amazon SNS               |
| sqs              | Amazon SQS               |
| ecs              | Amazon ECS               |
| eks              | Amazon EKS               |
| vpc              | Amazon VPC               |
| route53          | Amazon Route 53          |
| apigateway       | Amazon API Gateway       |
| dynamodb         | Amazon DynamoDB          |
| elasticache      | Amazon ElastiCache       |
| elb / elbv2      | Elastic Load Balancing (v2)|
| guardduty        | Amazon GuardDuty         |
| config           | AWS Config               |
| securityhub      | AWS Security Hub         |
| secretsmanager   | AWS Secrets Manager      |
| ssm              | AWS Systems Manager      |

Unknown service ids fall through to `f"AWS {svc.upper()}"` via
`_display_for()` — nothing crashes on an exotic service.

## 4. `RESOURCE_TERMS`

(singular, plural) noun for each service. Extract:

| Service id | Singular                | Plural                   |
|------------|-------------------------|--------------------------|
| s3         | bucket                  | buckets                  |
| iam        | IAM entity              | IAM entities             |
| ec2        | instance                | instances                |
| lambda     | function                | functions                |
| kms        | key                     | keys                     |
| dynamodb   | table                   | tables                   |
| vpc        | VPC                     | VPCs                     |
| elb(v2)    | load balancer           | load balancers           |

Unknown service ids fall back to `("resource", "resources")` via
`_terms_for()`.

## 5. Multi-service fallback

When `is_multi_service = True` and no service has `dominance_ratio >
0.7`, scope uses:

```python
GENERIC_FALLBACK = {
    "display":        "AWS Infrastructure",
    "term_singular":  "resource",
    "term_plural":    "resources",
}
```

This is what fixture G (`S3 + IAM + EC2`) produces — the rendered HTML
frames the scan as "AWS Infrastructure" and uses "resource(s)" throughout
the LLM-written sections.

## 6. `is_valid_resource(resource, service, account_id=None)`

Service-aware replacement for the old `_looks_like_bucket` helper. Used by
`ReportAgent._extract_distinct_resources` to count resources for the
cover page.

Rules:

| Service       | Accepted if…                                                   |
|---------------|-----------------------------------------------------------------|
| any           | length ≥ 3, not equal to the account id, not a pure digit string|
| `s3`          | … and does not start with `arn:`                                |
| `iam`         | starts with `arn:aws:iam` or contains `/` or is a valid identifier |
| `ec2`         | starts with `i-`, `sg-`, `vol-`, or `arn:aws:ec2`               |
| default       | any non-empty, non-numeric string                               |

The goal is to drop the classic "account-id leaking into the bucket list"
case (`123456789012` appearing where a bucket name should be) without
over-filtering obscure ARN shapes. Callers can tighten per-service rules
as more services come into scope.

## 7. Consumers

Every downstream consumer reads the same scope dict:

* [pdca/agents/report_agent.py](../pdca/agents/report_agent.py) —
  aggregation (`_build_system_data`), LLM section dispatch, validator
  construction.
* [pdca/agents/report_module/llm_writer.py](../pdca/agents/report_module/llm_writer.py)
  — every `write_*` method interpolates `scope_info["service_display"]` /
  `scope_info["resource_term"]` into the prompt.
* [pdca/agents/report_module/template.py](../pdca/agents/report_module/template.py)
  — cover page renders `scope_info["service_display"]`.
* [pdca/agents/report_module/validators.py](../pdca/agents/report_module/validators.py)
  — uses `scope_info["service_list"]` as the initial
  `allowed_services` seed (see `build_evidence`).
* [pdca/orchestrator.py](../pdca/orchestrator.py) — detects once,
  passes everywhere.

## 8. Extension points

Adding a new service requires three edits:

1. Add an entry to `SERVICE_DISPLAY`.
2. Add a `(singular, plural)` to `RESOURCE_TERMS` (falls back to
   `("resource", "resources")` if omitted).
3. If the service's resource identifiers have a shape not already
   covered, extend `is_valid_resource` with a matching rule.

No other file has to change — the prompt templates, validator, and
template picker all read from `scope_info` by key, not by hardcoded
service name.
