# Golden Set External Review Packet
**Instructions:** Paste this entire file into Claude or ChatGPT and ask:

> For each numbered entry below, decide whether the proposed `expected_capability_id` is the SINGLE best mapping for the given Prowler check from the capability catalog. Reply with a JSON array: `[{"id": <n>, "verdict": "agree|disagree|partial", "better_capability_id": "<id-or-null>", "comment": "<one sentence>"}, ...]`. Use ONLY capability_id values that appear in the catalog list provided.

## Capability catalog (78 ids, valid choices)

```
evaluate_resilience_posture_aws_resilience_hub
detect_common_threats
select_the_region_s_where_you_want_to_operate_and_block_the_rest
cleanup_unused_and_unintended_external_access_using_iam_access_analyzer_or_ciem_solutions
billing_alarms_for_anomaly_detection
1_quick_wins
block_public_access
cleanup_risky_open_admin_ports_in_security_groups
analyze_data_security_posture
waf_with_managed_rules
keep_your_security_contact_details_up_to_date
root_account_protection
audit_api_calls
identity_federation_centralized_user_repository
act_on_critical_security_findings
multi_factor_authentication
evaluate_cloud_security_posture_aws_security_hub
use_temporary_credentials
manage_vulnerabilities_in_your_infrastructure_and_perform_pentesting
data_encryption_at_rest
advanced_threat_detection
network_segmentation_vpcs_public_private_networks
don_t_store_secrets_in_code_remove_secrets_from_code
identify_security_and_regulatory_requirements
inventory_configurations_monitoring
define_incident_response_playbooks
discover_sensitive_data_with_amazon_macie
secure_ec2_instances_management
2_foundational
cloud_security_training_plan
instance_metadata_service_imds_v2
set_up_multi_account_management_with_aws_control_tower
achieve_redundancy_using_multiple_availability_zones
data_backups
limit_network_access_using_security_groups
manage_vulnerabilities_in_your_applications
involve_security_teams_in_development
permission_guardrails_organizational_policies_with_scps_and_rcps
construction_of_a_continuous_pipeline_for_golden_image_generation
use_infrastructure_as_code
create_your_compliance_reports
design_your_secure_architecture
advanced_waf_protection_with_custom_rules
build_a_security_champions_program
run_tabletop_exercises_simulations
3_efficient
devsecops_security_in_the_pipeline
anti_malware_edr_runtime_protection
least_privilege_review_set_up_right_size_permissions_in_roles
disaster_recovery_plan
customer_iam_security_of_your_customers
outbound_traffic_control
security_investigations_root_cause_analysis_with_amazon_detective
encryption_in_transit
advanced_ddos_mitigation_layer_7_aws_shield
automate_critical_and_the_most_frequently_executed_playbooks
custom_threat_detection_capabilities_siem_security_lake
tagging_strategy
threat_modeling
advanced_security_automations
temporary_elevated_access_management
4_optimized
zero_trust_access_risk_based_access_control
automate_evidence_gathering_for_compliance_audit_reports
multi_region_disaster_recovery_automation
iam_data_perimeters_conditional_access
automate_deviation_correction_in_configurations
sharing_security_tasks_and_responsibility_raci_matrix
form_a_vulnerability_management_team
forming_a_chaos_engineering_team
building_a_red_team_attacker_point_of_view
iam_policy_generation_pipeline
formation_of_a_blue_team_incident_response_team
security_orchestration_and_ticketing
threat_intelligence
using_abstract_services_serverless
vpc_flow_logs_analysis
generative_ai_data_protection_with_amazon_bedrock
```

## Already-verified golden mappings (context, do not re-review)

- `s3_bucket_default_encryption` → `data_encryption_at_rest`
- `s3_account_level_public_access_blocks` → `block_public_access`
- `iam_root_mfa_enabled` → `multi_factor_authentication`
- `iam_user_mfa_enabled_console_access` → `multi_factor_authentication`
- `iam_password_policy_minimum_length_14` → `multi_factor_authentication`
- `cloudtrail_multi_region_enabled` → `detect_common_threats`
- `cloudtrail_logs_s3_bucket_access_logging_enabled` → `detect_common_threats`
- `guardduty_is_enabled` → `advanced_threat_detection`
- `ec2_securitygroup_allow_ingress_from_internet_to_any_port` → `network_segmentation_vpcs_public_private_networks`
- `ec2_securitygroup_allow_ingress_from_internet_to_tcp_port_22` → `network_segmentation_vpcs_public_private_networks`
- `rds_instance_storage_encrypted` → `data_encryption_at_rest`
- `rds_instance_backup_enabled` → `data_backups`
- `ec2_instance_older_than_specific_days` → `manage_vulnerabilities_in_your_infrastructure_and_perform_pentesting`
- `cloudfront_distributions_https_sni_enabled` → `encryption_in_transit`
- `elbv2_ssl_listeners` → `encryption_in_transit`
- `vpc_flow_logs_enabled` → `detect_common_threats`
- `iam_root_hardware_mfa_enabled` → `multi_factor_authentication`
- `iam_no_root_access_key` → `iam_data_perimeters_conditional_access`
- `kms_cmk_rotation_enabled` → `data_encryption_at_rest`
- `ec2_ebs_default_encryption` → `data_encryption_at_rest`

## New mappings to review (30)

### 1. `efs_encryption_at_rest_enabled`

**Check title:** EFS file system has encryption at rest enabled

**Check description:** **Amazon EFS file system** has **encryption at rest** enabled using AWS KMS to protect file data and metadata stored on the service

**Check categories:** ['encryption']

**Proposed capability_id:** `data_encryption_at_rest`

**Proposed capability summary:** AWS services that store data enable you to encrypt your data using Server Side Encryption, so that the customer effort is minimal, that’s why Werner Vogels, Amazon.com CTO often says “Encrypt everything”. Ensure all critical data in your organization is encrypted. It’s recommended that you encrypt allsensitive data using your own encryption keyinstead of using AWS encryption keys, for that we prov

**Security domain:** data_protection

**Citations:** AWS_FSBP:EFS.1, NIST_800_53_R5:SC-28

**Rationale:** EFS at-rest encryption = data-at-rest control.

---

### 2. `sns_topics_kms_encryption_at_rest_enabled`

**Check title:** Ensure there are no SNS Topics unencrypted

**Check description:** Ensure there are no SNS Topics unencrypted

**Check categories:** ['encryption']

**Proposed capability_id:** `data_encryption_at_rest`

**Proposed capability summary:** AWS services that store data enable you to encrypt your data using Server Side Encryption, so that the customer effort is minimal, that’s why Werner Vogels, Amazon.com CTO often says “Encrypt everything”. Ensure all critical data in your organization is encrypted. It’s recommended that you encrypt allsensitive data using your own encryption keyinstead of using AWS encryption keys, for that we prov

**Security domain:** data_protection

**Citations:** AWS_FSBP:SNS.1, NIST_800_53_R5:SC-28

**Rationale:** SNS KMS encryption at rest.

---

### 3. `cloudtrail_kms_encryption_enabled`

**Check title:** CloudTrail trail logs are encrypted at rest with a KMS key

**Check description:** **AWS CloudTrail trails** are evaluated for use of **SSE-KMS** with a customer-managed KMS key to encrypt delivered log files at rest in S3. Trails without a configured KMS key are identified. *Applies to single-Region and multi-Region trails.*

**Check categories:** ['encryption']

**Proposed capability_id:** `data_encryption_at_rest`

**Proposed capability summary:** AWS services that store data enable you to encrypt your data using Server Side Encryption, so that the customer effort is minimal, that’s why Werner Vogels, Amazon.com CTO often says “Encrypt everything”. Ensure all critical data in your organization is encrypted. It’s recommended that you encrypt allsensitive data using your own encryption keyinstead of using AWS encryption keys, for that we prov

**Security domain:** data_protection

**Citations:** CIS_AWS_Foundations_v3.0.0:3.7, AWS_FSBP:CloudTrail.2

**Rationale:** KMS encryption for CloudTrail log data = data-at-rest.

---

### 4. `s3_bucket_object_lock`

**Check title:** Check if S3 buckets have object lock enabled

**Check description:** Check if S3 buckets have object lock enabled

**Check categories:** []

**Proposed capability_id:** `data_backups`

**Proposed capability summary:** Given the widespread of multiple malicious programs that encrypt information and ask for ransom (Ransomware), it is essential backup data to avoid losing any information. AWS Backup is a fully managed backup service that makes it easy to centralize and automate the backup of data across AWS services. By using AWS Backup, you can centrally configure backup policies and monitor backup activity for A

**Security domain:** resilience

**Citations:** NIST_800_53_R5:CP-9, NIST_800_53_R5:SI-7

**Rationale:** Object Lock provides WORM protection supporting backup/recovery integrity.

---

### 5. `s3_bucket_object_versioning`

**Check title:** Check if S3 buckets have object versioning enabled

**Check description:** Check if S3 buckets have object versioning enabled

**Check categories:** []

**Proposed capability_id:** `data_backups`

**Proposed capability summary:** Given the widespread of multiple malicious programs that encrypt information and ask for ransom (Ransomware), it is essential backup data to avoid losing any information. AWS Backup is a fully managed backup service that makes it easy to centralize and automate the backup of data across AWS services. By using AWS Backup, you can centrally configure backup policies and monitor backup activity for A

**Security domain:** resilience

**Citations:** AWS_FSBP:S3.14, NIST_800_53_R5:CP-9

**Rationale:** Versioning preserves prior object states — backup primitive.

---

### 6. `ec2_instance_account_imdsv2_enabled`

**Check title:** Ensure Instance Metadata Service Version 2 (IMDSv2) is enforced for EC2 instances at the account level to protect against SSRF vulnerabilities.

**Check description:** Ensure Instance Metadata Service Version 2 (IMDSv2) is enforced for EC2 instances at the account level to protect against SSRF vulnerabilities.

**Check categories:** ['internet-exposed']

**Proposed capability_id:** `instance_metadata_service_imds_v2`

**Proposed capability summary:** The Amazon Elastic Compute Cloud (Amazon EC2) Instance Metadata Service (IMDS) helps customers build secure and scalable applications. IMDS solves a security challenge for cloud users by providing access to temporary and frequently-rotated credentials, and by removing the need to hardcode or distribute sensitive credentials to instances manually or programmatically. The Instance Metadata Service V

**Security domain:** identity_access

**Citations:** AWS_FSBP:EC2.8

**Rationale:** Direct 1:1 match — IMDSv2 capability.

---

### 7. `ec2_instance_imdsv2_enabled`

**Check title:** Check if EC2 Instance Metadata Service Version 2 (IMDSv2) is Enabled and Required.

**Check description:** Check if EC2 Instance Metadata Service Version 2 (IMDSv2) is Enabled and Required.

**Check categories:** []

**Proposed capability_id:** `instance_metadata_service_imds_v2`

**Proposed capability summary:** The Amazon Elastic Compute Cloud (Amazon EC2) Instance Metadata Service (IMDS) helps customers build secure and scalable applications. IMDS solves a security challenge for cloud users by providing access to temporary and frequently-rotated credentials, and by removing the need to hardcode or distribute sensitive credentials to instances manually or programmatically. The Instance Metadata Service V

**Security domain:** identity_access

**Citations:** AWS_FSBP:EC2.8

**Rationale:** Per-instance IMDSv2 enforcement.

---

### 8. `iam_user_no_setup_initial_access_key`

**Check title:** Do not setup access keys during initial user setup for all IAM users that have a console password

**Check description:** Do not setup access keys during initial user setup for all IAM users that have a console password

**Check categories:** []

**Proposed capability_id:** `use_temporary_credentials`

**Proposed capability summary:** IAM users and Access Keys are long-term/durable credentials. These are not rotated until someone acts to rotate them. These credentials may used by recenlty terminated employees, if there was no record of them having (or being the owner) of those credentials. These credentials present multiple risks, therefore, we should avoid the use of IAM users and Access Keys whenever possible and should striv

**Security domain:** identity_access

**Citations:** AWS_FSBP:IAM.20, NIST_800_53_R5:AC-2

**Rationale:** No long-lived initial keys = enforce temporary-credentials posture.

---

### 9. `iam_password_policy_uppercase`

**Check title:** Ensure IAM password policy requires at least one uppercase letter

**Check description:** Ensure IAM password policy requires at least one uppercase letter

**Check categories:** []

**Proposed capability_id:** `multi_factor_authentication`

**Proposed capability summary:** You can use free virtual tokens such as Authy, Duo Mobile, Last Pass Authenticator, Google Authenticator, or Microsoft Authenticator. For security reasons it’s advisable to use multi-factor authenticationfor all users, starting with root and privileged users but ideally for all of them. For security reasons it’s advisable to use multi-factor authentication on every user authentication. If this aff

**Security domain:** identity_access

**Citations:** CIS_AWS_Foundations_v3.0.0:1.8, NIST_800_53_R5:IA-5(1)

**Rationale:** Password complexity is part of authentication hardening; closest capability.

---

### 10. `secretsmanager_automatic_rotation_enabled`

**Check title:** Check if Secrets Manager secret rotation is enabled.

**Check description:** Check if Secrets Manager secret rotation is enabled.

**Check categories:** []

**Proposed capability_id:** `don_t_store_secrets_in_code_remove_secrets_from_code`

**Proposed capability summary:** Storing secrets in code is a mistake that may cause a credential to be unintentionally exposed. If the hardcoded secrets are Access Keys, review the Use Temporary Credentialsrecommendation. If you need to access from your code to some service that useslong-term credentials, leverage AWS Secrets Managerto provide the credential when needed and handle rotation: It works in a similar way to what is e

**Security domain:** identity_access

**Citations:** AWS_FSBP:SecretsManager.1, NIST_800_53_R5:IA-5(7)

**Rationale:** Automatic secret rotation is the operational complement to not-storing-secrets-in-code.

---

### 11. `config_recorder_all_regions_enabled`

**Check title:** AWS Config recorder is enabled and not in failure state or disabled

**Check description:** **AWS accounts** have **AWS Config recorders** active and healthy in each Region. It identifies Regions with no recorder, a disabled recorder, or a recorder in a failure state.

**Check categories:** ['logging', 'forensics-ready']

**Proposed capability_id:** `inventory_configurations_monitoring`

**Proposed capability summary:** It is important to have an inventory of assets (at least at high level) of which applications are in each account, business process associated, and what type of resources they should have and significant security configurations that should be enforced. To maintain consistency on the alignment of security configurations to best practices it’s necessary to keep track of configuration changes in your

**Security domain:** logging_monitoring

**Citations:** CIS_AWS_Foundations_v3.0.0:3.5, AWS_FSBP:Config.1

**Rationale:** AWS Config records resource configuration over time — inventory/config monitoring.

---

### 12. `cloudtrail_log_file_validation_enabled`

**Check title:** CloudTrail trail has log file validation enabled

**Check description:** **AWS CloudTrail trails** are evaluated for **log file integrity validation** being enabled (`LogFileValidationEnabled`).

When enabled, CloudTrail generates signed digest files to verify that S3-delivered log files remain unchanged.

**Check categories:** ['logging', 'forensics-ready']

**Proposed capability_id:** `audit_api_calls`

**Proposed capability summary:** It is advisable to use AWS CloudTrail audit logs to investigate incidents by setting them to retain the logs for the period that your security policy determines. AWS CloudTrailEvent historyis available for all customers for free to view online for 90 days without any additional configuration. You should take a look at these logs and learn how to search and understand your logs there. Cloudtrail lo

**Security domain:** logging_monitoring

**Citations:** CIS_AWS_Foundations_v3.0.0:3.2, AWS_FSBP:CloudTrail.4

**Rationale:** Log file validation protects integrity of API audit trail.

---

### 13. `vpc_flow_logs_enabled`

**Check title:** Ensure VPC Flow Logging is Enabled in all VPCs.

**Check description:** Ensure VPC Flow Logging is Enabled in all VPCs.

**Check categories:** ['forensics-ready', 'logging']

**Proposed capability_id:** `vpc_flow_logs_analysis`

**Proposed capability summary:** In AWS you can monitor the flow of traffic looking at the metadata available in VPC Flow Logs, or if you need to do analysis of the complete traffic (Full packet capture), you can use Traffic Mirroring. Some SIEM solutionshave the capability of analyzing VPC Flow Logs (such as Splunk and QRadar). It’s possible to send the VPC Flow Logs to Amazon CloudWatch or through Amazon Kinesis Firehoseto an A

**Security domain:** logging_monitoring

**Citations:** CIS_AWS_Foundations_v3.0.0:3.9, AWS_FSBP:EC2.6

**Rationale:** Direct 1:1 — VPC flow logs capability.

---

### 14. `elb_logging_enabled`

**Check title:** Check if Elastic Load Balancers have logging enabled.

**Check description:** Check if Elastic Load Balancers have logging enabled.

**Check categories:** ['forensics-ready', 'logging']

**Proposed capability_id:** `audit_api_calls`

**Proposed capability summary:** It is advisable to use AWS CloudTrail audit logs to investigate incidents by setting them to retain the logs for the period that your security policy determines. AWS CloudTrailEvent historyis available for all customers for free to view online for 90 days without any additional configuration. You should take a look at these logs and learn how to search and understand your logs there. Cloudtrail lo

**Security domain:** logging_monitoring

**Citations:** AWS_FSBP:ELB.5

**Rationale:** ELB access logging extends audit chain to data plane (closest capability in catalog).

---

### 15. `shield_advanced_protection_in_route53_hosted_zones`

**Check title:** Check if Route53 hosted zones are protected by AWS Shield Advanced.

**Check description:** Check if Route53 hosted zones are protected by AWS Shield Advanced.

**Check categories:** []

**Proposed capability_id:** `advanced_ddos_mitigation_layer_7_aws_shield`

**Proposed capability summary:** AWS offers afree Denial of Service Attack Protection service called AWS Shield Standard, which is enabled on all accounts (even those that only use the Free tier). The service protects you against layer 3-4 volumetric attacks such as SYN floods and UDP reflection. Optionally, customers can choose to enable AWS Shield Advancedfor greater protection of their cloud loads. AWS Shield Advanced compleme

**Security domain:** network

**Citations:** AWS_FSBP:Shield.1

**Rationale:** Direct 1:1 — Shield Advanced on Route53.

---

### 16. `apigateway_restapi_waf_acl_attached`

**Check title:** API Gateway stage has a WAF Web ACL attached

**Check description:** **Amazon API Gateway (REST API)** stages are assessed for an associated **AWS WAF web ACL**. The finding reflects whether a `web ACL` is linked at the stage level.

**Check categories:** ['threat-detection']

**Proposed capability_id:** `waf_with_managed_rules`

**Proposed capability summary:** 

**Security domain:** network

**Citations:** AWS_FSBP:APIGateway.4

**Rationale:** WAF attachment to API Gateway = managed WAF rules deployment.

---

### 17. `awslambda_function_url_public`

**Check title:** Lambda function URL is not publicly accessible

**Check description:** **AWS Lambda function URLs** are assessed to determine whether `AuthType` enforces **AWS IAM authentication** or permits **public invocation**.

Applies to functions with a function URL and highlights when requests must be authenticated and authorized via IAM principals.

**Check categories:** ['internet-exposed']

**Proposed capability_id:** `block_public_access`

**Proposed capability summary:** 

**Security domain:** network

**Citations:** AWS_FSBP:Lambda.5

**Rationale:** Publicly accessible Lambda URL violates block-public-access posture.

---

### 18. `s3_bucket_public_access`

**Check title:** Ensure there are no S3 buckets open to Everyone or Any AWS user.

**Check description:** Ensure there are no S3 buckets open to Everyone or Any AWS user.

**Check categories:** ['internet-exposed']

**Proposed capability_id:** `block_public_access`

**Proposed capability summary:** 

**Security domain:** network

**Citations:** AWS_FSBP:S3.2, CIS_AWS_Foundations_v3.0.0:2.1.5

**Rationale:** Bucket-level public access block.

---

### 19. `organizations_scp_check_deny_regions`

**Check title:** Check if AWS Regions are restricted with SCP policies

**Check description:** As best practice, AWS Regions should be restricted and only allow the ones that are needed.

**Check categories:** []

**Proposed capability_id:** `select_the_region_s_where_you_want_to_operate_and_block_the_rest`

**Proposed capability summary:** Select the region(s) you want to use and disable the use of other regions in multiple accounts using AWS Organizationsthrough Service Control Policiesor if you have deployed AWS Control Towerselect the regions to use and block the restin the Landing Zone configuration. Documentation site with policy examples AWS Global Infrastructure Regions More Information about Service Control Policies is avail

**Security domain:** network

**Citations:** AWS_Well_Architected:SEC-BP02

**Rationale:** SCP region-deny implements region allowlist capability.

---

### 20. `rds_instance_deletion_protection`

**Check title:** Check if RDS instances have deletion protection enabled.

**Check description:** Check if RDS instances have deletion protection enabled.

**Check categories:** []

**Proposed capability_id:** `data_backups`

**Proposed capability summary:** Given the widespread of multiple malicious programs that encrypt information and ask for ransom (Ransomware), it is essential backup data to avoid losing any information. AWS Backup is a fully managed backup service that makes it easy to centralize and automate the backup of data across AWS services. By using AWS Backup, you can centrally configure backup policies and monitor backup activity for A

**Security domain:** resilience

**Citations:** AWS_FSBP:RDS.8

**Rationale:** Deletion protection is a recovery-readiness control adjacent to backups (closest in catalog).

---

### 21. `elasticache_redis_cluster_multi_az_enabled`

**Check title:** Ensure Elasticache Redis cache cluster has Multi-AZ enabled.

**Check description:** Ensure Elasticache Redis cache cluster has Multi-AZ enabled.

**Check categories:** ['redundancy']

**Proposed capability_id:** `achieve_redundancy_using_multiple_availability_zones`

**Proposed capability summary:** It is recommended that you use multiple Availability Zones to increase your fault tolerance and disaster resilience. Our AZs offer many resiliency capacities including having those AZs at 100km - 60 miles between AZs, so it’s rare for disasters in one AZ to spread to multiple AZs, and the distance is not too far to add significant latency. See more details about Availability Zones in here:https://

**Security domain:** resilience

**Citations:** AWS_Well_Architected:REL-BP-06

**Rationale:** Automatic failover requires multi-AZ redundancy.

---

### 22. `macie_is_enabled`

**Check title:** Check if Amazon Macie is enabled.

**Check description:** Check if Amazon Macie is enabled.

**Check categories:** ['forensics-ready']

**Proposed capability_id:** `discover_sensitive_data_with_amazon_macie`

**Proposed capability summary:** Among the organization controls there the definition of which data is more sensitive for the organization (the “crown jewels”), and identify where such data should be hosted. However, we often find sensitive data in additional places than where we expected it to be. Amazon Macie has data identifiers managed by AWS, i.e. rules/patterns to detect sensitive data (e.g. credit cards, id numbers, access

**Security domain:** data_protection

**Citations:** AWS_Well_Architected:SEC-BP-08

**Rationale:** Direct 1:1 — Macie capability.

---

### 23. `macie_automated_sensitive_data_discovery_enabled`

**Check title:** Check if Macie automated sensitive data discovery is enabled.

**Check description:** Check if automated sensitive data discovery is enabled for an Amazon Macie account. The control fails if it isn't enabled.

**Check categories:** []

**Proposed capability_id:** `discover_sensitive_data_with_amazon_macie`

**Proposed capability summary:** Among the organization controls there the definition of which data is more sensitive for the organization (the “crown jewels”), and identify where such data should be hosted. However, we often find sensitive data in additional places than where we expected it to be. Amazon Macie has data identifiers managed by AWS, i.e. rules/patterns to detect sensitive data (e.g. credit cards, id numbers, access

**Security domain:** data_protection

**Citations:** AWS_Well_Architected:SEC-BP-08

**Rationale:** Automated discovery is core to Macie capability.

---

### 24. `guardduty_no_high_severity_findings`

**Check title:** There are High severity GuardDuty findings 

**Check description:** There are High severity GuardDuty findings 

**Check categories:** []

**Proposed capability_id:** `act_on_critical_security_findings`

**Proposed capability summary:** It is recommended to configure alerts for critical findings mail messages sent via Amazon SNS, or via integrations using AWS Lambda to Instant messaging services such as Slack. Ensure someone on your organization is acting on critical security findings as they are detected. The improvement to the security posture that detective controls such as Amazon GuardDuty provide is only when there’s someone

**Security domain:** threat_detection

**Citations:** NIST_800_53_R5:IR-4

**Rationale:** Acting on high-severity GuardDuty findings = critical-finding response capability.

---

### 25. `inspector2_is_enabled`

**Check title:** Check if Inspector2 is enabled for Amazon EC2 instances, ECR container images and Lambda functions.

**Check description:** Ensure that the new version of Amazon Inspector is enabled in order to help you improve the security and compliance of your AWS cloud environment. Amazon Inspector 2 is a vulnerability management solution that continually scans scans your Amazon EC2 instances, ECR container images, and Lambda functions to identify software vulnerabilities and instances of unintended network exposure.

**Check categories:** []

**Proposed capability_id:** `manage_vulnerabilities_in_your_infrastructure_and_perform_pentesting`

**Proposed capability summary:** It’s recommended to use vulnerability management services such as Amazon Inspector to identify infrastructure vulnerabilities and deviations from the CIS OS hardening best practices on your instances. Amazon inspector delivers continuous vulnerability management, leveraging the same AWS Systems Manager Agent. Scanning your cloud resources with network sweeps as you would on-prem can be challenging

**Security domain:** vulnerability_management

**Citations:** AWS_FSBP:Inspector.1, NIST_800_53_R5:RA-5

**Rationale:** Inspector continuous scanning supports infrastructure vulnerability management.

---

### 26. `ecr_repositories_scan_images_on_push_enabled`

**Check title:** [DEPRECATED] Check if ECR image scan on push is enabled

**Check description:** [DEPRECATED] Check if ECR image scan on push is enabled

**Check categories:** []

**Proposed capability_id:** `manage_vulnerabilities_in_your_applications`

**Proposed capability summary:** It is recommended to use vulnerability scanning tools both for applications (Dynamic Application Security Testing - DAST), and code (Static Application Security Testing, SAST) and perform penetration testing on critical company applications and ideally on all of them. Application vulnerabilities are easier (and more cost efficient) to remediate when the developers are writing the code, but followi

**Security domain:** vulnerability_management

**Citations:** AWS_FSBP:ECR.1

**Rationale:** Image scanning on push = application vulnerability management at the artifact layer.

---

### 27. `bedrock_agent_guardrail_enabled`

**Check title:** Ensure that Guardrails are enabled for Amazon Bedrock agent sessions.

**Check description:** This check ensures that Guardrails are enabled to protect Amazon Bedrock agent sessions. Guardrails help mitigate security risks by filtering and blocking harmful or sensitive content during interactions with AI models.

**Check categories:** ['gen-ai']

**Proposed capability_id:** `generative_ai_data_protection_with_amazon_bedrock`

**Proposed capability summary:** Most organizations that are building Gen AI apps are concerned about how to protect the data they use to personalize or train their models, not only from threat actors attempting attacks such as Prompt injection, but also how to protect their data and prompts from the Foundational Model providers who may use their data to improve the model. Terms & Conditions may not be sufficient assurance for yo

**Security domain:** gen_ai

**Citations:** AWS_Bedrock_Best_Practices:-

**Rationale:** Guardrails are the primary Bedrock data-protection control.

---

### 28. `bedrock_model_invocation_logs_encryption_enabled`

**Check title:** Ensure that Amazon Bedrock model invocation logs are encrypted with KMS.

**Check description:** Ensure that Amazon Bedrock model invocation logs are encrypted using AWS KMS to protect sensitive data in the request and response logs for all model invocations.

**Check categories:** ['encryption', 'logging', 'gen-ai']

**Proposed capability_id:** `generative_ai_data_protection_with_amazon_bedrock`

**Proposed capability summary:** Most organizations that are building Gen AI apps are concerned about how to protect the data they use to personalize or train their models, not only from threat actors attempting attacks such as Prompt injection, but also how to protect their data and prompts from the Foundational Model providers who may use their data to improve the model. Terms & Conditions may not be sufficient assurance for yo

**Security domain:** gen_ai

**Citations:** AWS_Bedrock_Best_Practices:-

**Rationale:** Encrypting model-invocation logs protects GenAI prompt/response data.

---

### 29. `eks_cluster_uses_a_supported_version`

**Check title:** Ensure Kubernetes cluster runs on a supported Kubernetes version

**Check description:** Ensure Kubernetes cluster runs on a supported Kubernetes version

**Check categories:** ['vulnerabilities']

**Proposed capability_id:** `manage_vulnerabilities_in_your_infrastructure_and_perform_pentesting`

**Proposed capability summary:** It’s recommended to use vulnerability management services such as Amazon Inspector to identify infrastructure vulnerabilities and deviations from the CIS OS hardening best practices on your instances. Amazon inspector delivers continuous vulnerability management, leveraging the same AWS Systems Manager Agent. Scanning your cloud resources with network sweeps as you would on-prem can be challenging

**Security domain:** container_security

**Citations:** AWS_FSBP:EKS.2, NIST_800_53_R5:SI-2

**Rationale:** Supported K8s version = patch/version control for container infrastructure.

---

### 30. `guardduty_centrally_managed`

**Check title:** GuardDuty is centrally managed

**Check description:** GuardDuty is centrally managed

**Check categories:** []

**Proposed capability_id:** `advanced_threat_detection`

**Proposed capability summary:** A key task among foundational detective controls is to review most Amazon GuardDuty findings (or the tool you use for detecting active threats). In other words, not only take action on critical finding, but alsoevaluate why medium or low priority findings are being generated, to detect early attempts of compromise, reconnaissance, quickly block the adversary and activate the incident response plan

**Security domain:** threat_detection

**Citations:** AWS_FSBP:GuardDuty.4

**Rationale:** Centralized GuardDuty management is a maturity-level implementation of advanced threat detection.

---

