"""Build benchmark v4.0 — production-realistic test cases."""
import json
from pathlib import Path

OUTPUT = Path(__file__).resolve().parent.parent / "data" / "benchmarks" / "benchmark_cases.json"
F = ["generative_ai_data_protection_with_amazon_bedrock"]

benchmark = {
    "version": "4.0",
    "description": (
        "Production-realistic benchmark v4.0. Distribution mirrors actual traffic: "
        "35% check_id exact lookup (RiskEval/Report agents), "
        "10% check_id partial/fuzzy, "
        "25% agent-generated English queries (PlanningAgent), "
        "15% Vietnamese user input (mixed Viet-English), "
        "10% capability lookup, "
        "5% negative/edge cases."
    ),
    "check_cases": [],
    "maturity_cases": [],
}


def add_check(case_id, category, service, query, expected_doc_id,
              expected_capability_id, grades, min_confidence="medium"):
    benchmark["check_cases"].append({
        "case_id": case_id,
        "category": category,
        "service": service,
        "query": query,
        "expected_doc_id": expected_doc_id,
        "expected_capability_id": expected_capability_id,
        "forbidden_capability_ids": F,
        "expected_service": service,
        "min_confidence": min_confidence,
        "all_relevant_doc_ids": list(grades.keys()),
        "relevance_grades": grades,
    })


def add_maturity(case_id, category, query, expected_capability_id,
                 grades, min_confidence="medium"):
    doc_id = f"capability:{expected_capability_id}"
    benchmark["maturity_cases"].append({
        "case_id": case_id,
        "category": category,
        "service": None,
        "query": query,
        "expected_doc_id": doc_id,
        "expected_capability_id": expected_capability_id,
        "forbidden_capability_ids": F,
        "min_confidence": min_confidence,
        "all_relevant_doc_ids": list(grades.keys()),
        "relevance_grades": grades,
    })


# ================================================================
# CATEGORY 1: check_id_exact (25 cases, 35%)
# RiskEvaluation + Report agents pass exact check_ids
# ================================================================

# S3 (5)
add_check("chk_exact_01", "check_id_exact", "s3",
    "s3_bucket_public_access", "check:s3_bucket_public_access", "block_public_access",
    {"check:s3_bucket_public_access": 3, "check:s3_bucket_level_public_access_block": 2})
add_check("chk_exact_02", "check_id_exact", "s3",
    "s3_bucket_default_encryption", "check:s3_bucket_default_encryption", "data_encryption_at_rest",
    {"check:s3_bucket_default_encryption": 3, "check:s3_bucket_kms_encryption": 2})
add_check("chk_exact_03", "check_id_exact", "s3",
    "s3_bucket_policy_public_write_access", "check:s3_bucket_policy_public_write_access", "block_public_access",
    {"check:s3_bucket_policy_public_write_access": 3, "check:s3_bucket_public_write_acl": 2})
add_check("chk_exact_04", "check_id_exact", "s3",
    "s3_account_level_public_access_blocks", "check:s3_account_level_public_access_blocks", "block_public_access",
    {"check:s3_account_level_public_access_blocks": 3, "check:s3_bucket_level_public_access_block": 2})
add_check("chk_exact_05", "check_id_exact", "s3",
    "s3_bucket_secure_transport_policy", "check:s3_bucket_secure_transport_policy", "encryption_in_transit",
    {"check:s3_bucket_secure_transport_policy": 3}, min_confidence="high")

# IAM (5)
add_check("chk_exact_06", "check_id_exact", "iam",
    "iam_root_mfa_enabled", "check:iam_root_mfa_enabled", "multi_factor_authentication",
    {"check:iam_root_mfa_enabled": 3, "check:iam_root_hardware_mfa_enabled": 2})
add_check("chk_exact_07", "check_id_exact", "iam",
    "iam_no_root_access_key", "check:iam_no_root_access_key", "root_account_protection",
    {"check:iam_no_root_access_key": 3, "check:iam_user_no_setup_initial_access_key": 2})
add_check("chk_exact_08", "check_id_exact", "iam",
    "iam_password_policy_minimum_length_14", "check:iam_password_policy_minimum_length_14", "automate_deviation_correction_in_configurations",
    {"check:iam_password_policy_minimum_length_14": 3, "check:iam_password_policy_uppercase": 1, "check:iam_password_policy_symbol": 1})
add_check("chk_exact_09", "check_id_exact", "iam",
    "iam_avoid_root_usage", "check:iam_avoid_root_usage", "root_account_protection",
    {"check:iam_avoid_root_usage": 3})
add_check("chk_exact_10", "check_id_exact", "iam",
    "iam_user_mfa_enabled_console_access", "check:iam_user_mfa_enabled_console_access", "multi_factor_authentication",
    {"check:iam_user_mfa_enabled_console_access": 3, "check:iam_root_mfa_enabled": 1})

# EC2 (5)
add_check("chk_exact_11", "check_id_exact", "ec2",
    "ec2_securitygroup_allow_ingress_from_internet_to_tcp_port_22", "check:ec2_securitygroup_allow_ingress_from_internet_to_tcp_port_22", "cleanup_risky_open_admin_ports_in_security_groups",
    {"check:ec2_securitygroup_allow_ingress_from_internet_to_tcp_port_22": 3, "check:ec2_networkacl_allow_ingress_tcp_port_22": 2})
add_check("chk_exact_12", "check_id_exact", "ec2",
    "ec2_ebs_default_encryption", "check:ec2_ebs_default_encryption", "data_encryption_at_rest",
    {"check:ec2_ebs_default_encryption": 3, "check:ec2_ebs_volume_encryption": 2})
add_check("chk_exact_13", "check_id_exact", "ec2",
    "ec2_launch_template_imdsv2_required", "check:ec2_launch_template_imdsv2_required", "instance_metadata_service_imds_v2",
    {"check:ec2_launch_template_imdsv2_required": 3, "check:autoscaling_group_launch_configuration_requires_imdsv2": 2, "check:ec2_instance_account_imdsv2_enabled": 2})
add_check("chk_exact_14", "check_id_exact", "ec2",
    "ec2_instance_public_ip", "check:ec2_instance_public_ip", "block_public_access",
    {"check:ec2_instance_public_ip": 3, "check:ec2_launch_template_no_public_ip": 2})
add_check("chk_exact_15", "check_id_exact", "ec2",
    "ec2_securitygroup_allow_ingress_from_internet_to_tcp_port_3389", "check:ec2_securitygroup_allow_ingress_from_internet_to_tcp_port_3389", "cleanup_risky_open_admin_ports_in_security_groups",
    {"check:ec2_securitygroup_allow_ingress_from_internet_to_tcp_port_3389": 3, "check:ec2_instance_port_rdp_exposed_to_internet": 2})

# RDS (3)
add_check("chk_exact_16", "check_id_exact", "rds",
    "rds_instance_no_public_access", "check:rds_instance_no_public_access", "block_public_access",
    {"check:rds_instance_no_public_access": 3, "check:rds_snapshots_public_access": 1})
add_check("chk_exact_17", "check_id_exact", "rds",
    "rds_instance_storage_encrypted", "check:rds_instance_storage_encrypted", "data_encryption_at_rest",
    {"check:rds_instance_storage_encrypted": 3, "check:rds_cluster_storage_encrypted": 2})
add_check("chk_exact_18", "check_id_exact", "rds",
    "rds_instance_backup_enabled", "check:rds_instance_backup_enabled", "data_backups",
    {"check:rds_instance_backup_enabled": 3})

# CloudTrail (2)
add_check("chk_exact_19", "check_id_exact", "cloudtrail",
    "cloudtrail_multi_region_enabled", "check:cloudtrail_multi_region_enabled", "audit_api_calls",
    {"check:cloudtrail_multi_region_enabled": 3, "check:cloudtrail_multi_region_enabled_logging_management_events": 2})
add_check("chk_exact_20", "check_id_exact", "cloudtrail",
    "cloudtrail_kms_encryption_enabled", "check:cloudtrail_kms_encryption_enabled", "data_encryption_at_rest",
    {"check:cloudtrail_kms_encryption_enabled": 3})

# Other services (5)
add_check("chk_exact_21", "check_id_exact", "kms",
    "kms_cmk_rotation_enabled", "check:kms_cmk_rotation_enabled", "data_encryption_at_rest",
    {"check:kms_cmk_rotation_enabled": 3})
add_check("chk_exact_22", "check_id_exact", "guardduty",
    "guardduty_is_enabled", "check:guardduty_is_enabled", "detect_common_threats",
    {"check:guardduty_is_enabled": 3, "check:guardduty_centrally_managed": 2})
add_check("chk_exact_23", "check_id_exact", "vpc",
    "vpc_flow_logs_enabled", "check:vpc_flow_logs_enabled", "vpc_flow_logs_analysis",
    {"check:vpc_flow_logs_enabled": 3})
add_check("chk_exact_24", "check_id_exact", "awslambda",
    "awslambda_function_no_secrets_in_code", "check:awslambda_function_no_secrets_in_code", "don_t_store_secrets_in_code_remove_secrets_from_code",
    {"check:awslambda_function_no_secrets_in_code": 3, "check:awslambda_function_no_secrets_in_variables": 2})
add_check("chk_exact_25", "check_id_exact", "secretsmanager",
    "secretsmanager_automatic_rotation_enabled", "check:secretsmanager_automatic_rotation_enabled", "don_t_store_secrets_in_code_remove_secrets_from_code",
    {"check:secretsmanager_automatic_rotation_enabled": 3, "check:secretsmanager_secret_rotated_periodically": 2})


# ================================================================
# CATEGORY 2: check_id_partial (7 cases, 10%)
# Agent sends partial/fuzzy/short form
# ================================================================

add_check("chk_partial_01", "check_id_partial", "s3",
    "bucket_public_access", "check:s3_bucket_public_access", "block_public_access",
    {"check:s3_bucket_public_access": 3, "check:s3_bucket_level_public_access_block": 2, "check:s3_account_level_public_access_blocks": 1})
add_check("chk_partial_02", "check_id_partial", "iam",
    "root_mfa_enabled", "check:iam_root_mfa_enabled", "multi_factor_authentication",
    {"check:iam_root_mfa_enabled": 3, "check:iam_root_hardware_mfa_enabled": 2})
add_check("chk_partial_03", "check_id_partial", "ec2",
    "security group port 22", "check:ec2_securitygroup_allow_ingress_from_internet_to_tcp_port_22", "cleanup_risky_open_admin_ports_in_security_groups",
    {"check:ec2_securitygroup_allow_ingress_from_internet_to_tcp_port_22": 3, "check:ec2_instance_port_ssh_exposed_to_internet": 2, "check:ec2_networkacl_allow_ingress_tcp_port_22": 2}, min_confidence="low")
add_check("chk_partial_04", "check_id_partial", "rds",
    "rds public access", "check:rds_instance_no_public_access", "block_public_access",
    {"check:rds_instance_no_public_access": 3, "check:rds_snapshots_public_access": 2}, min_confidence="low")
add_check("chk_partial_05", "check_id_partial", "cloudtrail",
    "cloudtrail multi region", "check:cloudtrail_multi_region_enabled", "audit_api_calls",
    {"check:cloudtrail_multi_region_enabled": 3, "check:cloudtrail_multi_region_enabled_logging_management_events": 2})
add_check("chk_partial_06", "check_id_partial", "ec2",
    "ebs encryption", "check:ec2_ebs_default_encryption", "data_encryption_at_rest",
    {"check:ec2_ebs_default_encryption": 3, "check:ec2_ebs_volume_encryption": 2}, min_confidence="low")
add_check("chk_partial_07", "check_id_partial", "iam",
    "password policy length", "check:iam_password_policy_minimum_length_14", "automate_deviation_correction_in_configurations",
    {"check:iam_password_policy_minimum_length_14": 3, "check:iam_password_policy_uppercase": 1, "check:iam_password_policy_lowercase": 1}, min_confidence="low")


# ================================================================
# CATEGORY 3: agent_query (18 cases, 25%)
# PlanningAgent short English queries: "[service] [keywords]"
# ================================================================

add_check("chk_agent_01", "agent_query", "s3",
    "s3 public access check", "check:s3_bucket_public_access", "block_public_access",
    {"check:s3_bucket_public_access": 3, "check:s3_account_level_public_access_blocks": 2, "check:s3_bucket_level_public_access_block": 2, "check:s3_bucket_policy_public_write_access": 1})
add_check("chk_agent_02", "agent_query", "s3",
    "s3 encryption", "check:s3_bucket_default_encryption", "data_encryption_at_rest",
    {"check:s3_bucket_default_encryption": 3, "check:s3_bucket_kms_encryption": 2, "check:s3_bucket_secure_transport_policy": 1}, min_confidence="low")
add_check("chk_agent_03", "agent_query", "s3",
    "s3 bucket logging", "check:s3_bucket_server_access_logging_enabled", "audit_api_calls",
    {"check:s3_bucket_server_access_logging_enabled": 3, "check:s3_bucket_object_versioning": 1}, min_confidence="low")
add_check("chk_agent_04", "agent_query", "iam",
    "iam root access", "check:iam_avoid_root_usage", "root_account_protection",
    {"check:iam_avoid_root_usage": 3, "check:iam_no_root_access_key": 2, "check:iam_root_mfa_enabled": 2, "check:iam_root_hardware_mfa_enabled": 1}, min_confidence="low")
add_check("chk_agent_05", "agent_query", "iam",
    "iam unused access key", "check:iam_user_accesskey_unused", "cleanup_unused_and_unintended_external_access_using_iam_access_analyzer_or_ciem_solutions",
    {"check:iam_user_accesskey_unused": 3, "check:iam_rotate_access_key_90_days": 2, "check:iam_user_two_active_access_key": 1}, min_confidence="low")
add_check("chk_agent_06", "agent_query", "iam",
    "iam admin privileges policy", "check:iam_aws_attached_policy_no_administrative_privileges", "least_privilege_review_set_up_right_size_permissions_in_roles",
    {"check:iam_aws_attached_policy_no_administrative_privileges": 3, "check:iam_customer_attached_policy_no_administrative_privileges": 2, "check:iam_inline_policy_no_administrative_privileges": 2}, min_confidence="low")
add_check("chk_agent_07", "agent_query", "ec2",
    "ec2 security group open ports", "check:ec2_securitygroup_allow_ingress_from_internet_to_all_ports", "cleanup_risky_open_admin_ports_in_security_groups",
    {"check:ec2_securitygroup_allow_ingress_from_internet_to_all_ports": 3, "check:ec2_securitygroup_allow_ingress_from_internet_to_high_risk_tcp_ports": 2, "check:ec2_securitygroup_allow_ingress_from_internet_to_tcp_port_22": 1}, min_confidence="low")
add_check("chk_agent_08", "agent_query", "ec2",
    "ec2 imdsv2 metadata", "check:ec2_launch_template_imdsv2_required", "instance_metadata_service_imds_v2",
    {"check:ec2_launch_template_imdsv2_required": 3, "check:ec2_instance_account_imdsv2_enabled": 2, "check:autoscaling_group_launch_configuration_requires_imdsv2": 2})
add_check("chk_agent_09", "agent_query", "ec2",
    "ec2 public ip exposure", "check:ec2_instance_public_ip", "block_public_access",
    {"check:ec2_instance_public_ip": 3, "check:ec2_launch_template_no_public_ip": 2}, min_confidence="low")
add_check("chk_agent_10", "agent_query", "rds",
    "rds public access database", "check:rds_instance_no_public_access", "block_public_access",
    {"check:rds_instance_no_public_access": 3, "check:rds_snapshots_public_access": 2, "check:rds_instance_inside_vpc": 1}, min_confidence="low")
add_check("chk_agent_11", "agent_query", "rds",
    "rds storage encryption", "check:rds_instance_storage_encrypted", "data_encryption_at_rest",
    {"check:rds_instance_storage_encrypted": 3, "check:rds_cluster_storage_encrypted": 2})
add_check("chk_agent_12", "agent_query", "rds",
    "rds backup enabled", "check:rds_instance_backup_enabled", "data_backups",
    {"check:rds_instance_backup_enabled": 3})
add_check("chk_agent_13", "agent_query", "cloudtrail",
    "cloudtrail logging management events", "check:cloudtrail_multi_region_enabled_logging_management_events", "audit_api_calls",
    {"check:cloudtrail_multi_region_enabled_logging_management_events": 3, "check:cloudtrail_multi_region_enabled": 2})
add_check("chk_agent_14", "agent_query", "cloudtrail",
    "cloudtrail log validation", "check:cloudtrail_log_file_validation_enabled", "audit_api_calls",
    {"check:cloudtrail_log_file_validation_enabled": 3, "check:cloudtrail_kms_encryption_enabled": 1})
add_check("chk_agent_15", "agent_query", "guardduty",
    "guardduty enabled threat detection", "check:guardduty_is_enabled", "detect_common_threats",
    {"check:guardduty_is_enabled": 3, "check:guardduty_centrally_managed": 2})
add_check("chk_agent_16", "agent_query", "kms",
    "kms key rotation", "check:kms_cmk_rotation_enabled", "data_encryption_at_rest",
    {"check:kms_cmk_rotation_enabled": 3})
add_check("chk_agent_17", "agent_query", "vpc",
    "vpc flow logs enabled", "check:vpc_flow_logs_enabled", "vpc_flow_logs_analysis",
    {"check:vpc_flow_logs_enabled": 3})
add_check("chk_agent_18", "agent_query", "cloudfront",
    "cloudfront https enabled", "check:cloudfront_distributions_https_enabled", "encryption_in_transit",
    {"check:cloudfront_distributions_https_enabled": 3, "check:cloudfront_distributions_https_sni_enabled": 2})


# ================================================================
# CATEGORY 4: user_query_vi (10 cases, 15%)
# Vietnamese DevOps engineer typing in Slack/Teams
# Mix Vietnamese + English AWS terms naturally
# ================================================================

add_check("chk_vi_01", "user_query_vi", "s3",
    "ki\u1ec3m tra S3 bucket c\u00f3 b\u1ecb public kh\u00f4ng",
    "check:s3_bucket_public_access", "block_public_access",
    {"check:s3_bucket_public_access": 3, "check:s3_bucket_level_public_access_block": 2, "check:s3_account_level_public_access_blocks": 2, "check:s3_bucket_policy_public_write_access": 1}, min_confidence="low")
add_check("chk_vi_02", "user_query_vi", "s3",
    "S3 ch\u01b0a b\u1eadt encryption",
    "check:s3_bucket_default_encryption", "data_encryption_at_rest",
    {"check:s3_bucket_default_encryption": 3, "check:s3_bucket_kms_encryption": 2}, min_confidence="low")
add_check("chk_vi_03", "user_query_vi", "iam",
    "t\u00e0i kho\u1ea3n root ch\u01b0a b\u1eadt MFA",
    "check:iam_root_mfa_enabled", "multi_factor_authentication",
    {"check:iam_root_mfa_enabled": 3, "check:iam_root_hardware_mfa_enabled": 2, "check:iam_avoid_root_usage": 1}, min_confidence="low")
add_check("chk_vi_04", "user_query_vi", "ec2",
    "security group m\u1edf port SSH ra ngo\u00e0i",
    "check:ec2_securitygroup_allow_ingress_from_internet_to_tcp_port_22", "cleanup_risky_open_admin_ports_in_security_groups",
    {"check:ec2_securitygroup_allow_ingress_from_internet_to_tcp_port_22": 3, "check:ec2_instance_port_ssh_exposed_to_internet": 2, "check:ec2_networkacl_allow_ingress_tcp_port_22": 2}, min_confidence="low")
add_check("chk_vi_05", "user_query_vi", "rds",
    "RDS database b\u1ecb public access",
    "check:rds_instance_no_public_access", "block_public_access",
    {"check:rds_instance_no_public_access": 3, "check:rds_snapshots_public_access": 2}, min_confidence="low")
add_check("chk_vi_06", "user_query_vi", "ec2",
    "EBS volume ch\u01b0a \u0111\u01b0\u1ee3c m\u00e3 h\u00f3a",
    "check:ec2_ebs_default_encryption", "data_encryption_at_rest",
    {"check:ec2_ebs_default_encryption": 3, "check:ec2_ebs_volume_encryption": 2}, min_confidence="low")
add_check("chk_vi_07", "user_query_vi", "iam",
    "IAM user c\u00f3 access key kh\u00f4ng d\u00f9ng",
    "check:iam_user_accesskey_unused", "cleanup_unused_and_unintended_external_access_using_iam_access_analyzer_or_ciem_solutions",
    {"check:iam_user_accesskey_unused": 3, "check:iam_rotate_access_key_90_days": 2}, min_confidence="low")
add_check("chk_vi_08", "user_query_vi", "cloudtrail",
    "b\u1eadt CloudTrail \u1edf t\u1ea5t c\u1ea3 region",
    "check:cloudtrail_multi_region_enabled", "audit_api_calls",
    {"check:cloudtrail_multi_region_enabled": 3, "check:cloudtrail_multi_region_enabled_logging_management_events": 2}, min_confidence="low")
add_check("chk_vi_09", "user_query_vi", "ec2",
    "EC2 instance c\u00f3 public IP",
    "check:ec2_instance_public_ip", "block_public_access",
    {"check:ec2_instance_public_ip": 3, "check:ec2_launch_template_no_public_ip": 2}, min_confidence="low")
add_check("chk_vi_10", "user_query_vi", "guardduty",
    "b\u1eadt GuardDuty cho t\u1ea5t c\u1ea3 account",
    "check:guardduty_is_enabled", "detect_common_threats",
    {"check:guardduty_is_enabled": 3, "check:guardduty_centrally_managed": 2}, min_confidence="low")


# ================================================================
# CATEGORY 5: capability_lookup (7 maturity cases, 10%)
# ================================================================

add_maturity("cap_exact_01", "capability_exact",
    "block_public_access", "block_public_access",
    {"capability:block_public_access": 3}, min_confidence="high")
add_maturity("cap_exact_02", "capability_exact",
    "data_encryption_at_rest", "data_encryption_at_rest",
    {"capability:data_encryption_at_rest": 3}, min_confidence="high")
add_maturity("cap_exact_03", "capability_exact",
    "root_account_protection", "root_account_protection",
    {"capability:root_account_protection": 3}, min_confidence="high")
add_maturity("cap_vi_01", "capability_vi",
    "b\u1ea3o v\u1ec7 d\u1eef li\u1ec7u l\u01b0u tr\u1eef b\u1eb1ng m\u00e3 h\u00f3a",
    "data_encryption_at_rest",
    {"capability:data_encryption_at_rest": 3}, min_confidence="low")
add_maturity("cap_vi_02", "capability_vi",
    "sao l\u01b0u v\u00e0 ph\u1ee5c h\u1ed3i data",
    "data_backups",
    {"capability:data_backups": 3, "capability:disaster_recovery_plan": 1}, min_confidence="low")
add_maturity("cap_vi_03", "capability_vi",
    "qu\u1ea3n l\u00fd nhi\u1ec1u AWS account t\u1eadp trung",
    "set_up_multi_account_management_with_aws_control_tower",
    {"capability:set_up_multi_account_management_with_aws_control_tower": 3}, min_confidence="low")
add_maturity("cap_agent_01", "capability_query",
    "least privilege access permissions", "least_privilege_review_set_up_right_size_permissions_in_roles",
    {"capability:least_privilege_review_set_up_right_size_permissions_in_roles": 3,
     "capability:cleanup_unused_and_unintended_external_access_using_iam_access_analyzer_or_ciem_solutions": 2}, min_confidence="low")


# ================================================================
# CATEGORY 6: negative/edge (3 cases, 5%)
# System should return low confidence or empty
# ================================================================

benchmark["check_cases"].append({
    "case_id": "chk_neg_01", "category": "negative", "service": None,
    "query": "check azure firewall rules",
    "expected_doc_id": None, "expected_capability_id": None,
    "forbidden_capability_ids": F, "expected_service": None,
    "min_confidence": "low",
    "all_relevant_doc_ids": [], "relevance_grades": {},
})
benchmark["check_cases"].append({
    "case_id": "chk_neg_02", "category": "negative", "service": None,
    "query": "",
    "expected_doc_id": None, "expected_capability_id": None,
    "forbidden_capability_ids": F, "expected_service": None,
    "min_confidence": "low",
    "all_relevant_doc_ids": [], "relevance_grades": {},
})
benchmark["check_cases"].append({
    "case_id": "chk_neg_03", "category": "negative", "service": None,
    "query": "xyznonexistent_check_id_12345",
    "expected_doc_id": None, "expected_capability_id": None,
    "forbidden_capability_ids": F, "expected_service": None,
    "min_confidence": "low",
    "all_relevant_doc_ids": [], "relevance_grades": {},
})


# ================================================================
# WRITE + STATS
# ================================================================

from collections import Counter

cc = Counter(c["category"] for c in benchmark["check_cases"])
mc = Counter(c["category"] for c in benchmark["maturity_cases"])
total = len(benchmark["check_cases"]) + len(benchmark["maturity_cases"])
vi = sum(
    1 for c in benchmark["check_cases"] + benchmark["maturity_cases"]
    if any(ord(ch) > 127 for ch in c.get("query", ""))
)

print(f"Total: {total} cases")
print(f"  Check cases: {len(benchmark['check_cases'])}")
for cat, n in sorted(cc.items()):
    print(f"    {cat}: {n} ({n/total*100:.0f}%)")
print(f"  Maturity cases: {len(benchmark['maturity_cases'])}")
for cat, n in sorted(mc.items()):
    print(f"    {cat}: {n} ({n/total*100:.0f}%)")
print(f"  Vietnamese: {vi} ({vi/total*100:.0f}%)")
print(f"  English: {total-vi} ({(total-vi)/total*100:.0f}%)")

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
with open(OUTPUT, "w", encoding="utf-8") as f:
    json.dump(benchmark, f, indent=2, ensure_ascii=False)
print(f"\nWritten: {OUTPUT}")
