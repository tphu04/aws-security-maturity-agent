# aws_smm_data.py

# Dữ liệu Tiêu chuẩn Đánh giá Độ trưởng thành Bảo mật AWS (AWS Security Maturity Model - SMM)
# Dữ liệu này mô phỏng các Document được truy vấn từ Vector Database (VDB).
# Mỗi document chứa một Capability (Khả năng) và các kiểm tra Prowler liên quan.

SMM_DOCUMENTS = [
    # =======================================================
    # DOMAIN: SECURITY GOVERNANCE
    # =======================================================
    {
        "domain": "Security Governance",
        "capability": "Assign Security Contacts",
        "level": 1,
        "description": "Cần chỉ định và ghi lại các địa chỉ liên hệ bảo mật chính thức cho tài khoản AWS.",
        "prowler_checks_map": ["account_security_contacts_defined"],
    },
    {
        "domain": "Security Governance",
        "capability": "Select the region(s) to use and block the rest",
        "level": 1,
        "description": "Cần hạn chế các khu vực AWS được sử dụng thông qua Service Control Policies (SCPs) hoặc các cơ chế tương đương để giảm thiểu bề mặt tấn công.",
        "prowler_checks_map": ["iam_policy_allow_regions_restriction"],
    },
    {
        "domain": "Security Governance",
        "capability": "Cloud Security Training Plan",
        "level": 2,
        "description": "Cần có kế hoạch đào tạo bảo mật đám mây cơ bản cho nhân viên.",
        "prowler_checks_map": [
            "general_security_training_placeholder"
        ],  # Không có check trực tiếp, chỉ là checklist
    },
    # =======================================================
    # DOMAIN: SECURITY ASSURANCE
    # =======================================================
    {
        "domain": "Security Assurance",
        "capability": "Evaluate Cloud Security Posture (CSPM)",
        "level": 1,
        "description": "Cần triển khai và thường xuyên đánh giá tư thế bảo mật bằng các công cụ CSPM (như Security Hub, Config).",
        "prowler_checks_map": ["securityhub_enabled", "config_recorder_enabled"],
    },
    {
        "domain": "Security Assurance",
        "capability": "Inventory & Configuration monitoring",
        "level": 2,
        "description": "Cần theo dõi và ghi lại tất cả tài nguyên và cấu hình thay đổi thông qua AWS Config hoặc CloudTrail.",
        "prowler_checks_map": [
            "config_recorder_enabled",
            "cloudtrail_enabled_all_regions",
        ],
    },
    # =======================================================
    # DOMAIN: IDENTITY AND ACCESS MANAGEMENT (IAM)
    # =======================================================
    {
        "domain": "Identity and Access Management",
        "capability": "Multi-Factor Authentication",
        "level": 1,
        "description": "Tất cả các tài khoản có quyền truy cập (đặc biệt Root và user IAM) phải sử dụng Multi-Factor Authentication (MFA).",
        "prowler_checks_map": ["iam_root_mfa_enabled", "iam_user_mfa_enabled"],
    },
    {
        "domain": "Identity and Access Management",
        "capability": "Root Account Protection",
        "level": 1,
        "description": "Tài khoản Root không được sử dụng cho các tác vụ hàng ngày và không được có Access Key hoạt động.",
        "prowler_checks_map": ["iam_root_access_key_check", "iam_root_use"],
    },
    {
        "domain": "Identity and Access Management",
        "capability": "Temporary Credentials",
        "level": 2,
        "description": "Ưu tiên sử dụng thông tin đăng nhập tạm thời (IAM Roles) thay vì Access Key dài hạn.",
        "prowler_checks_map": ["iam_user_no_long_lived_access_keys"],
    },
    # =======================================================
    # DOMAIN: THREAT DETECTION
    # =======================================================
    {
        "domain": "Threat Detection",
        "capability": "Detect Common Threats",
        "level": 1,
        "description": "Cần kích hoạt GuardDuty để phát hiện các mối đe dọa phổ biến và cấu hình cảnh báo cho các hành động quan trọng (ví dụ: truy cập Root).",
        "prowler_checks_map": [
            "guardduty_enabled_in_all_regions",
            "cloudtrail_root_api_calls_enabled",
        ],
    },
    {
        "domain": "Threat Detection",
        "capability": "Advanced Threat Detection",
        "level": 2,
        "description": "Cần giám sát các nhật ký chi tiết như VPC Flow Logs để phân tích lưu lượng mạng và phát hiện các hành vi bất thường.",
        "prowler_checks_map": ["vpc_flow_logs_enabled"],
    },
    # =======================================================
    # DOMAIN: INFRASTRUCTURE PROTECTION
    # =======================================================
    {
        "domain": "Infrastructure Protection",
        "capability": "Cleanup risky open ports",
        "level": 1,
        "description": "Các Security Groups (SGs) không được mở cổng quản lý (như SSH port 22, RDP port 3389) ra Internet (0.0.0.0/0).",
        "prowler_checks_map": [
            "ec2_securitygroup_any_ingress_to_tcp_22",
            "ec2_securitygroup_any_ingress_to_tcp_3389",
        ],
    },
    {
        "domain": "Infrastructure Protection",
        "capability": "Network Segmentation (VPCs)",
        "level": 2,
        "description": "Cần sử dụng các Network ACLs (NACLs) để kiểm soát lưu lượng truy cập ở cấp độ Subnet.",
        "prowler_checks_map": ["vpc_networkacl_allow_all_ingress"],
    },
    # =======================================================
    # DOMAIN: DATA PROTECTION
    # (Đã cập nhật từ file trước)
    # =======================================================
    {
        "domain": "Data Protection",
        "capability": "Block Public Access",
        "level": 1,
        "description": "Phải kích hoạt Block Public Access ở cấp độ Account để ngăn chặn rò rỉ dữ liệu.",
        "prowler_checks_map": [
            "s3_account_level_public_access_blocks",
            "s3_bucket_public_access",
        ],
    },
    {
        "domain": "Data Protection",
        "capability": "Data Encryption at Rest",
        "level": 2,
        "description": "Tất cả các tài nguyên lưu trữ (như S3) phải được mã hóa bằng SSE-S3 hoặc KMS.",
        "prowler_checks_map": ["s3_bucket_default_encryption"],
    },
    {
        "domain": "Data Protection",
        "capability": "Backups (Resiliency)",
        "level": 2,
        "description": "Các tài nguyên S3 quan trọng phải có Versioning được kích hoạt để cho phép phục hồi sau lỗi hoặc hành động xóa nhầm.",
        "prowler_checks_map": ["s3_bucket_object_versioning"],
    },
    # =======================================================
    # DOMAIN: INCIDENT RESPONSE
    # =======================================================
    {
        "domain": "Incident Response",
        "capability": "Act on Critical Security Findings",
        "level": 1,
        "description": "Cần có cơ chế cảnh báo tự động hoặc thủ công cho các phát hiện bảo mật có mức độ nghiêm trọng 'Critical' hoặc 'High'.",
        "prowler_checks_map": ["securityhub_alerts_critical_and_high"],
    },
    # =======================================================
    # DOMAIN: RESILIENCY
    # =======================================================
    {
        "domain": "Resiliency",
        "capability": "Evaluate Resilience (General)",
        "level": 1,
        "description": "Cần có các biện pháp cơ bản để duy trì tính khả dụng (availability) của các dịch vụ cốt lõi, ví dụ như kích hoạt Versioning trên S3 để ngăn chặn mất dữ liệu.",
        "prowler_checks_map": ["s3_bucket_object_versioning"],
    },
]


class SMMRetriever:
    """
    Mô phỏng chức năng tra cứu của Vector Database (VDB).
    (CẬP NHẬT) Giờ đây hỗ trợ tra cứu trực tiếp bằng Prowler Check ID.
    """

    def __init__(self):
        self.documents = SMM_DOCUMENTS
        # (MỚI) Tạo một map để tra cứu Prowler -> SMM
        self._build_prowler_map()

    def _build_prowler_map(self):
        """
        (Hàm nội bộ mới)
        Xây dựng một dictionary để map Prowler Check ID -> SMM Document.
        Ví dụ: {'iam_root_mfa_enabled': {SMM_DOCUMENT_CỦA_NÓ}}
        """
        self.prowler_map = {}
        for doc in self.documents:
            # Lấy danh sách các check Prowler từ document
            prowler_checks = doc.get("prowler_checks_map", [])
            for check_id in prowler_checks:
                # Gán check_id này với document của nó
                # Nếu 1 check_id bị trùng (ví dụ s3_bucket_object_versioning)
                # nó sẽ bị ghi đè, nhưng trong ngữ cảnh này là chấp nhận được.
                self.prowler_map[check_id] = doc

    def search_by_prowler_check(self, prowler_check_id: str) -> dict | None:
        """
        (HÀM MỚI QUAN TRỌNG)
        Tra cứu SMM Document dựa trên Prowler Check ID (ví dụ: 'iam_root_mfa_enabled').
        Trả về 1 dictionary (document) hoặc None nếu không tìm thấy.
        """
        # Sử dụng map đã xây dựng để tra cứu O(1) (rất nhanh)
        return self.prowler_map.get(prowler_check_id)

    def retrieve_by_domain(self, domain_name: str) -> list:
        """
        (Hàm cũ của bạn, giữ nguyên nếu bạn vẫn cần)
        Trả về các tài liệu SMM liên quan đến một Domain nhất định.
        """
        domain_name = domain_name.lower().strip()
        search_domains = [
            "security governance",
            "security assurance",
            "identity and access management",
            "threat detection",
            "vulnerability management",
            "infrastructure protection",
            "data protection",
            "application security",
            "incident response",
            "resiliency",
        ]
        matched_domains = [
            d
            for d in search_domains
            if domain_name in d.lower() or d.lower().startswith(domain_name)
        ]
        results = []
        if matched_domains:
            for d_name in matched_domains:
                results.extend(
                    [doc for doc in self.documents if doc["domain"].lower() == d_name]
                )

        # (Logic format của bạn)
        unique_results = []
        seen_capabilities = set()
        for doc in results:
            cap_id = (doc["domain"], doc["capability"], doc["level"])
            if cap_id not in seen_capabilities:
                unique_results.append(doc)
                seen_capabilities.add(cap_id)

        formatted_results = []
        for doc in unique_results:
            prowler_map = ", ".join(doc.get("prowler_checks_map", []))
            formatted_results.append(
                f"DOMAIN: {doc['domain']}\nCAPABILITY: {doc['capability']} (Maturity Level {doc['level']})\nCHECKLIST: {doc['description']}\nPROWLER MAP: {prowler_map}"
            )
        return formatted_results
