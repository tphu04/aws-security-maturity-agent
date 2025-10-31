import ollama
import json
import os
import time
import requests
from dotenv import load_dotenv

# -------------------------------------------------------------------
# BƯỚC 1: CẤU HÌNH CLIENT OLLAMA (Giữ nguyên)
# -------------------------------------------------------------------

load_dotenv()
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3")
client = ollama.Client()
API_SERVER_URL = "http://127.0.0.1:8000"

# -------------------------------------------------------------------
# BƯỚC 2: ĐỊNH NGHĨA CÁC "TOOL" PHÍA CLIENT (Giữ nguyên)
# -------------------------------------------------------------------


def start_scan_by_group(group: str):
    """
    [TOOL] Bắt đầu một công việc quét tài khoản AWS theo TÊN SERVICE (group).
    Ví dụ: 's3', 'iam', 'ec2'.
    """
    print(f"[Tool Call] ⚡️ Đang gọi API: /scan/check?group={group}")
    try:
        response = requests.get(f"{API_SERVER_URL}/scan/check", params={"group": group})
        response.raise_for_status()
        return response.text
    except requests.exceptions.ConnectionError:
        return json.dumps(
            {
                "error": "Không thể kết nối đến API server. Bạn đã chạy 'uvicorn main:app' chưa?"
            }
        )
    except requests.exceptions.RequestException as e:
        return json.dumps(
            {
                "error": f"Lỗi API: {str(e)}",
                "details": e.response.text if e.response else "N/A",
            }
        )


def start_scan_by_file(filename: str):
    """
    [TOOL] Bắt đầu một công việc quét tài khoản AWS theo TÊN FILE JSON tùy chỉnh.
    File JSON này phải tồn tại trong thư mục 'custom_checks' trên server.
    """
    print(f"[Tool Call] ⚡️ Đang gọi API: /scan/custom?filename={filename}")
    try:
        response = requests.get(
            f"{API_SERVER_URL}/scan/custom", params={"filename": filename}
        )
        response.raise_for_status()
        return response.text
    except requests.exceptions.ConnectionError:
        return json.dumps({"error": "Không thể kết nối đến API server."})
    except requests.exceptions.RequestException as e:
        return json.dumps(
            {
                "error": f"Lỗi API: {str(e)}",
                "details": e.response.text if e.response else "N/A",
            }
        )


def check_job_status(job_id: str):
    """
    [TOOL] Kiểm tra trạng thái của một công việc (job) quét AWS đã được bắt đầu.
    """
    print(f"[Tool Call] ⚡️ Đang gọi API: /job/status?job_id={job_id}")
    try:
        response = requests.get(
            f"{API_SERVER_URL}/job/status", params={"job_id": job_id}
        )
        response.raise_for_status()
        return response.text
    except requests.exceptions.ConnectionError:
        return json.dumps({"error": "Không thể kết nối đến API server."})
    except requests.exceptions.RequestException as e:
        return json.dumps(
            {
                "error": f"Lỗi API: {str(e)}",
                "details": e.response.text if e.response else "N/A",
            }
        )


available_tools = {
    "start_scan_by_group": start_scan_by_group,
    "start_scan_by_file": start_scan_by_file,
    "check_job_status": check_job_status,
}

# -------------------------------------------------------------------
# BƯỚC 3: "THỰC ĐƠN" TOOL CHO AI (Giữ nguyên)
# -------------------------------------------------------------------
tools_menu = [
    {
        "type": "function",
        "function": {
            "name": "start_scan_by_group",
            "description": "Bắt đầu quét AWS theo tên service (group). Ví dụ: 's3', 'iam', 'ec2'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "group": {
                        "type": "string",
                        "description": "Tên service AWS để quét, ví dụ 's3', 'iam'.",
                    }
                },
                "required": ["group"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "start_scan_by_file",
            "description": "Bắt đầu quét AWS theo tên file JSON tùy chỉnh (ví dụ 'my_checks.json').",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Tên file JSON trong thư mục custom_checks.",
                    }
                },
                "required": ["filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_job_status",
            "description": "Kiểm tra trạng thái của một job đang chạy bằng 'job_id' của nó.",
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {
                        "type": "string",
                        "description": "Mã ID của job được trả về từ các hàm 'start_scan'.",
                    }
                },
                "required": ["job_id"],
            },
        },
    },
]

# -------------------------------------------------------------------
# BƯỚC 4: VÒNG LẶP AI ĐIỀU PHỐI (ORCHESTRATOR LOOP) - ĐÃ NÂNG CẤP
# -------------------------------------------------------------------


def run_ai_conversation_loop(user_prompt: str):
    print(f"👤 Người dùng: {user_prompt}\n")

    system_prompt = """
    Bạn là một trợ lý AI điều khiển công cụ Prowler.
    1. Bắt đầu bằng cách gọi `start_scan_by_group` hoặc `start_scan_by_file`.
    2. Từ chuỗi JSON kết quả, hãy tìm đến trường Assessment.Findings. Đếm số lượng phần tử trong mảng đó để có tổng số finding. Sau đó, duyệt qua từng phần tử, lấy giá trị của trường Severity.Label và đếm số lần xuất hiện của mỗi loại (High, Medium, Low).
    3. Sau khi một job hoàn thành, hãy tóm tắt kết quả cho người dùng một cách rõ ràng bao gồm số findings, số pass/fail, thống kê theo từng mức độ nguy cơ.
    """

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    model_name = OLLAMA_MODEL
    print(f"Sử dụng model Ollama: {model_name}")

    # <-- MỚI: Biến để theo dõi job đang chạy
    active_job_id = None

    while True:
        print(f"--------------------------------------------------")

        # <-- LOGIC MỚI: Ưu tiên kiểm tra job đang chạy
        if active_job_id:
            print(
                f"⚙️ Mã điều phối: Đang theo dõi job '{active_job_id}'. Kiểm tra trạng thái..."
            )

            # Tự động gọi hàm check_job_status mà không cần AI
            status_response_str = check_job_status(job_id=active_job_id)
            print(f"   <- API trả về: {status_response_str[:200]}...")

            try:
                status_data = json.loads(status_response_str)
                job_status = status_data.get("status")

                if job_status in ["completed", "failed"]:
                    print(
                        f"✅ Mã điều phối: Job '{active_job_id}' đã kết thúc với trạng thái '{job_status}'."
                    )
                    print("   -> Đưa kết quả cho AI để tóm tắt.")

                    # Đưa kết quả vào tin nhắn và để AI xử lý ở bước tiếp theo
                    messages.append({"role": "tool", "content": status_response_str})
                    active_job_id = None  # Xóa job khỏi danh sách theo dõi

                elif job_status in ["running", "pending"]:
                    print(
                        f"⏳ Mã điều phối: Job '{active_job_id}' vẫn đang '{job_status}'. Chờ 15 giây..."
                    )
                    time.sleep(15)
                    continue  # Bỏ qua lượt gọi AI và lặp lại để kiểm tra status

                else:  # Xử lý các trường hợp lỗi khác
                    print(
                        f"⚠️ Mã điều phối: Trạng thái không xác định '{job_status}'. Đưa lỗi cho AI."
                    )
                    messages.append({"role": "tool", "content": status_response_str})
                    active_job_id = None

            except json.JSONDecodeError:
                print(f"❌ Mã điều phối: Lỗi khi đọc kết quả status. Đưa lỗi cho AI.")
                messages.append({"role": "tool", "content": status_response_str})
                active_job_id = None

        # <-- LOGIC CŨ: Chỉ chạy khi không có job nào đang được theo dõi
        print(f"🤖 Gọi AI... (Lịch sử hiện có {len(messages)} tin nhắn)")
        try:
            response = client.chat(
                model=model_name, messages=messages, tools=tools_menu
            )
        except Exception as e:
            print(f"\n[LỖI] Không thể gọi Ollama: {e}")
            break

        response_message = response["message"]
        messages.append(response_message)
        tool_calls = response_message.get("tool_calls")

        if tool_calls:
            # AI muốn gọi tool (thường là để bắt đầu một scan mới)
            print(f"🤖 AI muốn gọi {len(tool_calls)} tool(s)...")
            for tool_call in tool_calls:
                function_name = tool_call["function"]["name"]
                function_args = tool_call["function"]["arguments"]
                print(f"   -> Đang gọi hàm: {function_name}(**{function_args})")

                function_to_call = available_tools.get(function_name)
                if function_to_call:
                    function_response_str = function_to_call(**function_args)
                    messages.append({"role": "tool", "content": function_response_str})
                    print(f"   <- API trả về: {function_response_str[:200]}...")

                    # <-- MỚI: Nếu tool được gọi là start_scan, lưu lại job_id
                    if function_name.startswith("start_scan"):
                        try:
                            response_data = json.loads(function_response_str)
                            if "job_id" in response_data:
                                active_job_id = response_data["job_id"]
                                print(
                                    f"📌 Mã điều phối: Đã bắt đầu job mới. Sẽ theo dõi '{active_job_id}'."
                                )
                        except json.JSONDecodeError:
                            print("⚠️ Mã điều phối: Không thể lấy job_id từ phản hồi.")
        else:
            # AI trả lời cuối cùng
            final_answer = response_message["content"]
            print(f"\n==================================================")
            print(f"💬 AI trả lời (cuối): {final_answer}")
            print(f"==================================================")
            break


# -------------------------------------------------------------------
# BƯỚC 5: CHẠY THỬ
# -------------------------------------------------------------------
if __name__ == "__main__":
    run_ai_conversation_loop(
        "Chào bạn, hãy quét s3 cho tôi. "
        "Hãy báo cáo kết quả cuối cùng của job đó cho tôi."
    )
