"""
Lab Simulator — Interactive Terminal CLI

Pure CLI execution environment for AI20k Lab Simulator.
Enables students to experience case study simulations, converse with Socratic Mentor,
teach naive PairPal, explore codebases via tools, and submit technical decisions.
"""

import sys
import os
from pathlib import Path

# Ensure UTF-8 output on Windows console
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if sys.stdin.encoding and sys.stdin.encoding.lower() != "utf-8":
    try:
        sys.stdin.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from simulator.providers import get_provider
from simulator.agent import run_agent_turn, SIMBOT_SYSTEM_PROMPT, MENTOR_SYSTEM_PROMPT, PAIRPAL_SYSTEM_PROMPT
from simulator.tools import TOOL_FUNCTIONS, TOOLS_SCHEMA
from simulator.evaluator import HybridEvaluator, EvalMetrics
from simulator.scenario import DAY01_SCENARIO, Scenario, RoundDef


class LabSimulatorCLI:
    def __init__(self, provider_name: str = "gemini", api_key: str = "", model: str = ""):
        self.provider = get_provider(provider_name, api_key=api_key, model=model)
        self.evaluator = HybridEvaluator(self.provider)
        self.scenario: Scenario = DAY01_SCENARIO
        self.current_round_idx: int = 0
        self.history_metrics: list[EvalMetrics] = []
        self.teaching_scores: list[int] = []
        self.mentor_history: list[dict[str, str]] = []
        self.pairpal_history: list[dict[str, str]] = []

    def print_banner(self, text: str, char: str = "="):
        line = char * min(80, len(text) + 6)
        print(f"\n{line}")
        print(f"  {text}")
        print(f"{line}\n")

    def print_box(self, title: str, content: str):
        print(f"\n┌── [ {title} ] " + "─" * max(0, 65 - len(title)))
        for c_line in content.splitlines():
            print(f"│  {c_line}")
        print("└" + "─" * 75)

    def start(self):
        self.print_banner(f"AI20K LAB SIMULATOR · {self.scenario.title}")
        print(self.scenario.briefing)
        print("\n🎯 [MỤC TIÊU CỦA PHIÊN SIMULATION]:")
        for i, obj in enumerate(self.scenario.objectives, 1):
            print(f"  {i}. {obj}")

        print("\n💡 Các lệnh hữu ích trong phiên làm việc:")
        print("  • /mentor <câu hỏi>      : Hỏi Trợ giảng Socratic (sẽ trích dẫn bài giảng [Txx-NNN])")
        print("  • /pairpal <giải thích>  : Trò chuyện và dạy cho bạn học PairPal (Protégé Effect)")
        print("  • /tools <lệnh> <args>   : Dùng tool kiểm tra bài lab (list_files, read_file, search_code)")
        print("  • /submit                : Gửi quyết định / code cho vòng hiện tại")
        print("  • /status                : Xem lại tiến độ và bảng điểm các vòng")
        print("  • /help                  : Xem lại danh sách lệnh")
        print("  • /quit                  : Thoát mô phỏng\n")

        while self.current_round_idx < len(self.scenario.rounds):
            self.run_current_round()

        self.run_final_debrief()

    def run_current_round(self):
        round_def: RoundDef = self.scenario.rounds[self.current_round_idx]
        self.print_banner(f"VÒNG {round_def.number}: {round_def.title}", "-")
        print(f"📋 Nhiệm vụ: {round_def.description}")
        print(f"🎯 Mục tiêu vòng: {round_def.objective}\n")

        # PairPal introduces misconception
        if round_def.pairpal_prompt:
            self.print_box("🧑‍🤝‍🧑 PairPal (Bạn học hỏi bạn)", round_def.pairpal_prompt)

        while True:
            try:
                raw = input(f"\n[Vòng {round_def.number} - Nhập lệnh hoặc /submit]> ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nĐã hủy phiên làm việc.")
                sys.exit(0)

            if not raw:
                continue

            if raw.lower() == "/quit":
                print("Tạm biệt! Hẹn gặp lại trong bài lab tiếp theo.")
                sys.exit(0)
            elif raw.lower() == "/help":
                print("\nLệnh có sẵn:")
                print("  /mentor <câu hỏi>      - Hỏi Trợ giảng Socratic")
                print("  /pairpal <giải thích>  - Giải thích cho PairPal")
                print("  /tools <cmd> <args>    - Tra cứu code bài lab")
                print("  /submit                - Nộp quyết định cho vòng này")
                print("  /status                - Bảng điểm hiện tại")
            elif raw.lower().startswith("/mentor"):
                query = raw[7:].strip()
                if not query:
                    print("⚠️ Hãy nhập câu hỏi, ví dụ: /mentor Giúp mình hiểu về trade-off temperature với")
                else:
                    self.ask_mentor(query)
            elif raw.lower().startswith("/pairpal"):
                explanation = raw[8:].strip()
                if not explanation:
                    print("⚠️ Hãy nhập lời giải thích, ví dụ: /pairpal Temperature không phải làm model thông minh hơn mà là...")
                else:
                    self.teach_pairpal(explanation, round_def)
            elif raw.lower().startswith("/tools"):
                tool_cmd = raw[6:].strip()
                self.execute_cli_tool(tool_cmd)
            elif raw.lower() == "/status":
                self.show_status()
            elif raw.lower() == "/submit":
                success = self.handle_submission(round_def)
                if success:
                    self.current_round_idx += 1
                    break
            else:
                print("⚠️ Lệnh không rõ. Nhập /help để xem các lệnh, hoặc /submit để nộp quyết định.")

    def ask_mentor(self, query: str):
        print("\n🔍 Mentor đang tra cứu codebase và bài giảng liên quan...")
        self.mentor_history.append({"role": "user", "content": query})

        def on_tool(name, args):
            print(f"   ↳ 🛠️ [Mentor Tool Call]: {name}({args})")

        res = run_agent_turn(
            provider=self.provider,
            messages=self.mentor_history,
            system_prompt=MENTOR_SYSTEM_PROMPT,
            temperature=0.2,
            on_tool_call=on_tool,
        )
        self.mentor_history.append({"role": "assistant", "content": res.text})
        self.print_box("🎓 Mentor (Trợ giảng Socratic)", res.text)

    def teach_pairpal(self, explanation: str, round_def: RoundDef):
        print("\n🤔 PairPal đang suy nghĩ về lời giải thích của bạn...")
        self.pairpal_history.append({"role": "user", "content": explanation})

        # Evaluate teaching effectiveness
        score, fb = self.evaluator.evaluate_teaching(
            student_explanation=explanation,
            misconception_topic=round_def.title,
        )
        self.teaching_scores.append(score)

        def on_tool(name, args):
            print(f"   ↳ 🛠️ [PairPal Tool Call]: {name}({args})")

        res = run_agent_turn(
            provider=self.provider,
            messages=self.pairpal_history,
            system_prompt=PAIRPAL_SYSTEM_PROMPT,
            temperature=0.4,
            on_tool_call=on_tool,
        )
        self.pairpal_history.append({"role": "assistant", "content": res.text})
        self.print_box("🧑‍🤝‍🧑 PairPal (Phản hồi của bạn học)", res.text)
        print(f"📊 [Điểm hiệu quả giảng giải (Teaching Score)]: {score}/100 — {fb}")

    def execute_cli_tool(self, cmd_line: str):
        parts = cmd_line.split()
        if not parts:
            print("Cách dùng:")
            print("  /tools list_files <lab>")
            print("  /tools read_file <lab> <file_path>")
            print("  /tools search_code <lab> <query>")
            print("  /tools summary <lab> <file_path>")
            print("  /tools transcript <query>")
            print("  /tools misconceptions <concept>")
            return

        cmd = parts[0].lower()
        args = parts[1:]

        if cmd == "list_files":
            lab = args[0] if args else "day01"
            res = TOOL_FUNCTIONS["list_files"](lab=lab)
            print(f"\n📂 Files trong {lab}:")
            for e in res.get("entries", []):
                print(f"  • [{e['type'].upper()}] {e['path']} ({e.get('size_bytes', 0)} bytes)")
        elif cmd == "read_file":
            if len(args) < 2:
                print("⚠️ Cần truyền: /tools read_file <lab> <file_path>")
                return
            lab, fpath = args[0], args[1]
            res = TOOL_FUNCTIONS["read_file"](lab=lab, file_path=fpath)
            if res.get("status") == "success":
                self.print_box(f"FILE: {fpath} ({res.get('showing')})", res.get("content", ""))
            else:
                print(f"❌ Lỗi: {res.get('message')}")
        elif cmd == "search_code":
            if len(args) < 2:
                print("⚠️ Cần truyền: /tools search_code <lab> <query>")
                return
            lab, query = args[0], " ".join(args[1:])
            res = TOOL_FUNCTIONS["search_code"](lab=lab, query=query)
            print(f"\n🔍 Kết quả tìm kiếm '{query}' trong {lab}: {res.get('match_count')} kết quả:")
            for m in res.get("results", []):
                print(f"  • {m['file']}:{m['line']} → {m['content']}")
        elif cmd == "transcript":
            query = " ".join(args) if args else "temperature"
            res = TOOL_FUNCTIONS["search_transcript"](query=query)
            print(f"\n🎙️ Trích đoạn bài giảng về '{query}':")
            for r in res.get("results", [])[:5]:
                print(f"  • {r['segment_ref']} ({r['transcript']}): {r['snippet']}")
        elif cmd == "misconceptions":
            concept = " ".join(args) if args else ""
            res = TOOL_FUNCTIONS["get_misconceptions"](concept=concept)
            print(f"\n💡 Các hiểu lầm phổ biến:")
            for mc in res.get("misconceptions", []):
                print(f"  [{mc['id']}] Khái niệm: {mc['concept']}")
                print(f"      ❌ Hiểu sai: {mc['wrong']}")
                print(f"      ✅ Đúng là: {mc['correct']}")
        else:
            print(f"⚠️ Lệnh tool không hỗ trợ: {cmd}")

    def handle_submission(self, round_def: RoundDef) -> bool:
        self.print_banner(f"NỘP QUYẾT ĐỊNH CHO VÒNG {round_def.number}", "=")

        if round_def.number == 1:
            print("Các lựa chọn model: gpt-4o, gpt-4o-mini, gemini-2.5-flash")
            model_choice = input("1. Chọn Model: ").strip() or "gpt-4o-mini"
            try:
                temp_val = float(input("2. Chọn Temperature (0.0 đến 1.5): ").strip() or "0.2")
            except ValueError:
                temp_val = 0.2
            rationale = input("3. Giải thích ngắn gọn lý do kỹ thuật đằng sau lựa chọn này: ").strip()

            print("\n⏳ Đang chạy Hybrid Evaluator (tính toán chi phí, độ trễ, accuracy và đánh giá lập luận)...")
            metrics = self.evaluator.evaluate_round1(model_choice, temp_val, rationale)

        elif round_def.number == 2:
            print("Nhập System Prompt của bạn (hỗ trợ nhiều dòng, kết thúc bằng gõ 'END' trên dòng mới):")
            lines = []
            while True:
                line = input()
                if line.strip() == "END":
                    break
                lines.append(line)
            system_prompt = "\n".join(lines).strip()
            rationale = input("Giải thích lý do cấu trúc prompt như trên: ").strip()

            print("\n⏳ Đang chạy Hybrid Evaluator...")
            metrics = self.evaluator.evaluate_round2(system_prompt, rationale)

        elif round_def.number == 3:
            print("Nhập đoạn code Python của bạn (kết thúc bằng gõ 'END' trên dòng mới):")
            lines = []
            while True:
                line = input()
                if line.strip() == "END":
                    break
                lines.append(line)
            code_snippet = "\n".join(lines).strip()
            rationale = input("Giải thích cách đoạn code xử lý lỗi và an toàn: ").strip()

            print("\n⏳ Đang thực thi mã nguồn và chấm điểm...")
            metrics = self.evaluator.evaluate_round3_code(code_snippet, rationale)
        else:
            return True

        self.history_metrics.append(metrics)
        self.display_metrics_table(round_def.number, metrics)

        # SimBot narrative feedback
        narrative_prompt = f"""Tóm tắt kết quả của học viên ở Vòng {round_def.number}:
Accuracy: {metrics.accuracy*100:.1f}%
Cost/query: ${metrics.cost_per_query:.5f}
Latency: {metrics.latency_ms:.0f}ms
Hallucination Rate: {metrics.hallucination_rate*100:.1f}%
Reasoning Quality: {metrics.reasoning_quality}/100
Chi tiết: {'; '.join(metrics.details)}

Hãy đưa ra phản hồi tường thuật (narrative feedback) ngắn gọn, sinh động như một người quản lý kỹ thuật đang báo cáo tình hình chatbot sau khi áp dụng thay đổi."""

        simbot_turn = run_agent_turn(
            provider=self.provider,
            messages=[{"role": "user", "content": narrative_prompt}],
            system_prompt=SIMBOT_SYSTEM_PROMPT,
            temperature=0.3,
        )
        self.print_box("🤖 SimBot (Báo cáo kết quả)", simbot_turn.text)

        confirm = input("\nBạn có muốn chuyển sang vòng tiếp theo? [Y/n]: ").strip().lower()
        return confirm != "n"

    def display_metrics_table(self, round_num: int, m: EvalMetrics):
        print(f"\n📊 ═══════════ [ BẢNG ĐIỂM VÒNG {round_num} ] ═══════════")
        print(f"  • Trạng thái vượt qua (Passed) : {'✅ ĐẠT' if m.passed else '⚠️ CHƯA ĐẠT'}")
        print(f"  • Độ chính xác (Accuracy)     : {m.accuracy*100:.1f}%")
        print(f"  • Chi phí mỗi lượt (Cost)     : ${m.cost_per_query:.5f} USD")
        print(f"  • Độ trễ phản hồi (Latency)   : {m.latency_ms:.0f} ms")
        print(f"  • Tỷ lệ Hallucination         : {m.hallucination_rate*100:.1f}%")
        print(f"  • Điểm lập luận (Reasoning)   : {m.reasoning_quality}/100")
        print("  • Chi tiết đánh giá:")
        for d in m.details:
            print(f"    - {d}")
        print("═" * 55)

    def show_status(self):
        print("\n📈 [TIẾN ĐỘ VÀ LỊCH SỬ CÁC VÒNG]:")
        for i, m in enumerate(self.history_metrics, 1):
            print(f"  Vòng {i}: Acc={m.accuracy*100:.1f}%, Cost=${m.cost_per_query:.5f}, Reasoning={m.reasoning_quality}/100, Passed={m.passed}")
        if self.teaching_scores:
            avg_teach = sum(self.teaching_scores) / len(self.teaching_scores)
            print(f"  Điểm giảng dạy PairPal trung bình: {avg_teach:.1f}/100")

    def run_final_debrief(self):
        self.print_banner("KẾT THÚC MÔ PHỎNG · BẢNG TỔNG KẾT HỌC TẬP (DEBRIEF)", "★")
        total_rounds = len(self.history_metrics)
        passed_rounds = sum(1 for m in self.history_metrics if m.passed)

        avg_acc = sum(m.accuracy for m in self.history_metrics) / total_rounds if total_rounds else 0
        avg_reasoning = sum(m.reasoning_quality for m in self.history_metrics) / total_rounds if total_rounds else 0
        avg_teaching = sum(self.teaching_scores) / len(self.teaching_scores) if self.teaching_scores else 0

        print(f"🏆 Tổng số vòng hoàn thành : {total_rounds}/{len(self.scenario.rounds)}")
        print(f"✅ Số vòng đạt chuẩn       : {passed_rounds}/{total_rounds}")
        print(f"🎯 Độ chính xác trung bình : {avg_acc*100:.1f}%")
        print(f"🧠 Điểm lập luận kỹ thuật  : {avg_reasoning:.1f}/100")
        print(f"🧑‍🤝‍🧑 Hiệu quả dạy PairPal   : {avg_teaching:.1f}/100")

        # Track D Learning Indicator
        print("\n🎓 [ĐÁNH GIÁ CHỈ SỐ HỌC TẬP (TRACK D)]: ")
        if avg_reasoning >= 70 and avg_teaching >= 65:
            print("  🌟 XUẤT SẮC: Bạn đã thể hiện tư duy trade-off vững chắc và khả năng truyền đạt sâu sắc!")
        elif avg_acc >= 0.70:
            print("  👍 TỐT: Hệ thống đạt mục tiêu kỹ thuật, có thể củng cố thêm khả năng giải thích bản chất.")
        else:
            print("  🌱 CẦN CẢI THIỆN: Hãy thử lại phiên mô phỏng để tối ưu hoá chi phí và giảm hallucination.")

        print("\nCảm ơn bạn đã tham gia Lab Simulator. Toàn bộ phiên làm việc đã hoàn thành thành công!\n")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="AI20K Lab Simulator CLI")
    parser.add_argument("--provider", default="gemini", help="LLM Provider: gemini, openai, mock")
    parser.add_argument("--api-key", default="", help="API Key override")
    parser.add_argument("--model", default="", help="Model override")
    args = parser.parse_args()

    cli = LabSimulatorCLI(provider_name=args.provider, api_key=args.api_key, model=args.model)
    cli.start()


if __name__ == "__main__":
    main()
