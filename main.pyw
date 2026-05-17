import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk
import glob, os, sys, threading, time
import pyautogui
import cv2
import numpy as np
import pygame

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# b1 = 열차 목록 '예매하기' 버튼
# b2 = 예매 진행 버튼
# b3 = 예매 클릭 버튼 (지정 범위에서 탐색)
# b4 = 예매 완료 화면 (발견 시 성공 → 알림음)
# s1.mp3 = 성공 알림음

pyautogui.FAILSAFE = True
pygame.mixer.init()

SRT_RED   = "#C8002D"
SRT_DARK  = "#1a1a2e"
SRT_NAV   = "#16213e"
SRT_BTN   = "#0f3460"
SRT_GREEN = "#64ffda"
SRT_GOLD  = "#ffd700"
SRT_GRAY  = "#8892b0"

PREV_W, PREV_H = 88, 62


def find_image_file(prefix):
    for ext in ("png", "jpg", "jpeg", "bmp"):
        p = os.path.join(BASE_DIR, f"{prefix}.{ext}")
        if os.path.exists(p):
            return p
    return None


# ── 화면 범위 선택 오버레이 ─────────────────────────────────────
class RegionSelector(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.region = None
        self._sx = self._sy = 0
        self.attributes("-fullscreen", True)
        self.attributes("-alpha", 0.25)
        self.attributes("-topmost", True)
        self.configure(bg="black", cursor="crosshair")
        self.overrideredirect(True)
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.canvas = tk.Canvas(self, width=sw, height=sh,
                                bg="black", highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_text(sw // 2, 30, fill="white",
                                font=("Malgun Gothic", 14, "bold"),
                                text="드래그하여 검색 범위를 지정하세요  (ESC: 취소)")
        self._rect = None
        self.canvas.bind("<ButtonPress-1>",   self._on_press)
        self.canvas.bind("<B1-Motion>",       self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Escape>", lambda e: self.destroy())

    def _on_press(self, e):
        self._sx, self._sy = e.x, e.y
        if self._rect:
            self.canvas.delete(self._rect)

    def _on_drag(self, e):
        if self._rect:
            self.canvas.delete(self._rect)
        self._rect = self.canvas.create_rectangle(
            self._sx, self._sy, e.x, e.y,
            outline=SRT_RED, width=2, fill="white", stipple="gray25")

    def _on_release(self, e):
        x1, y1 = min(self._sx, e.x), min(self._sy, e.y)
        x2, y2 = max(self._sx, e.x), max(self._sy, e.y)
        w, h = x2 - x1, y2 - y1
        if w > 10 and h > 10:
            self.region = (x1, y1, w, h)
        self.destroy()


# ── 메인 앱 ────────────────────────────────────────────────────
class SRTMacroApp:
    def __init__(self, root):
        self.root = root
        self.root.title("SRT 자동 예매 매크로")
        self.root.geometry("420x960+0+0")
        self.root.resizable(False, False)
        self.root.configure(bg=SRT_DARK)
        self.root.attributes("-topmost", True)

        self._macro_running  = False
        self._search_thread  = None
        self._region         = None
        self._preview_canvas = {}
        self._preview_photo  = {}

        self._build_ui()
        self.root.update_idletasks()
        h = self.root.winfo_reqheight()
        self.root.geometry(f"420x{h}+0+0")
        self.root.bind("<F12>", lambda e: self.stop_macro())

        # 시작 시 안내 팝업
        self.root.after(200, self._startup_notice)

    def _startup_notice(self):
        messagebox.showwarning(
            "⚠  중요 안내",
            "차종구분을 SRT+KTX에서\n"
            "SRT 로 변경하셔야합니다!\n\n"
            "SRT 사이트 → 일반승차권 조회\n"
            "→ 차종구분: SRT 선택 후 이용하세요."
        )

    # ── UI 빌드 ─────────────────────────────────────────────────
    def _build_ui(self):
        # 헤더
        header = tk.Frame(self.root, bg=SRT_NAV, pady=12)
        header.pack(fill="x")
        tk.Label(header, text="SRT 자동 예매 매크로",
                 font=("Malgun Gothic", 15, "bold"),
                 bg=SRT_NAV, fg=SRT_RED).pack()
        tk.Label(header, text="수서발 고속철도 자동화 프로그램",
                 font=("Malgun Gothic", 9),
                 bg=SRT_NAV, fg=SRT_GRAY).pack()

        # 상태 표시
        sf = tk.Frame(self.root, bg=SRT_DARK, padx=16, pady=5)
        sf.pack(fill="x")
        tk.Label(sf, text="상태:", font=("Malgun Gothic", 9),
                 bg=SRT_DARK, fg=SRT_GRAY).pack(side="left")
        self.status_var = tk.StringVar(value="대기 중")
        self.status_label = tk.Label(sf, textvariable=self.status_var,
                                     font=("Malgun Gothic", 9, "bold"),
                                     bg=SRT_DARK, fg=SRT_GREEN)
        self.status_label.pack(side="left", padx=4)

        tk.Frame(self.root, height=1, bg=SRT_GRAY).pack(fill="x", padx=16, pady=2)

        # 매크로 시작 버튼
        bf = tk.Frame(self.root, bg=SRT_DARK, padx=16, pady=6)
        bf.pack(fill="x")
        tk.Button(bf, text="🚄  SRT 좌석 매크로 시작",
                  font=("Malgun Gothic", 12, "bold"),
                  bg=SRT_BTN, fg="white", activebackground="#533483",
                  relief="flat", cursor="hand2", height=2,
                  command=self.start_seat_macro).pack(fill="x")

        tk.Frame(self.root, height=1, bg=SRT_GRAY).pack(fill="x", padx=16, pady=4)

        # ── 이미지 캡처 + 미리보기 (b1~b4, 2×2 그리드) ──────────
        sec = tk.Frame(self.root, bg=SRT_DARK, padx=16, pady=4)
        sec.pack(fill="x")
        tk.Label(sec,
                 text="이미지 지정  (미리보기 클릭 → 크게 보기 / 버튼 클릭 → 캡처)",
                 font=("Malgun Gothic", 8, "bold"),
                 bg=SRT_DARK, fg=SRT_GRAY).pack(anchor="w", pady=(0, 6))

        grid = tk.Frame(sec, bg=SRT_DARK)
        grid.pack(fill="x")

        LABELS = {
            "b1": "b1 이미지지정",
            "b2": "b2 이미지지정",
            "b3": "b3 이미지지정",
            "b4": "b4 이미지지정",
            "b5": "b5 이미지지정",
        }

        for i, (prefix, btn_label) in enumerate(LABELS.items()):
            row, col = divmod(i, 2)
            cell = tk.Frame(grid, bg=SRT_NAV, padx=4, pady=4)
            cell.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")

            # 미리보기 캔버스 (클릭 → 크게 보기)
            cv = tk.Canvas(cell, width=PREV_W, height=PREV_H,
                           bg="#0d0d1a", highlightthickness=1,
                           highlightbackground=SRT_GRAY, cursor="hand2")
            cv.pack()
            cv.bind("<Button-1>", lambda e, p=prefix: self._show_large_preview(p))
            self._preview_canvas[prefix] = cv
            self._draw_preview(prefix)

            # 캡처 버튼
            tk.Button(cell, text=btn_label,
                      font=("Malgun Gothic", 8, "bold"),
                      bg="#0d2233", fg=SRT_GREEN,
                      relief="flat", cursor="hand2", height=2,
                      command=lambda p=prefix: self._capture_image(p)
                      ).pack(fill="x", pady=(3, 0))

        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        tk.Frame(self.root, height=1, bg=SRT_GRAY).pack(fill="x", padx=16, pady=6)

        # 매크로 종료 버튼
        sf2 = tk.Frame(self.root, bg=SRT_DARK, padx=16)
        sf2.pack(fill="x")
        tk.Button(sf2, text="⏹  매크로 종료  (F12)",
                  font=("Malgun Gothic", 13, "bold"),
                  bg=SRT_RED, fg="white", activebackground="#8b0020",
                  relief="flat", cursor="hand2", height=2,
                  command=self.stop_macro).pack(fill="x")

        tk.Frame(self.root, height=1, bg=SRT_GRAY).pack(fill="x", padx=16, pady=6)

        # 로그 영역 (10줄)
        lf = tk.Frame(self.root, bg=SRT_NAV, padx=8, pady=6)
        lf.pack(fill="x", padx=16, pady=(0, 4))
        tk.Label(lf, text="로그", font=("Malgun Gothic", 8),
                 bg=SRT_NAV, fg=SRT_GRAY).pack(anchor="w")
        self.log_text = tk.Text(lf, height=8,
                                bg="#0d0d1a", fg=SRT_GREEN,
                                font=("Consolas", 10),
                                relief="flat", state="disabled", wrap="word")
        self.log_text.pack(fill="both", expand=True)

        # 프로그램 종료
        tk.Button(self.root, text="✖  프로그램 종료",
                  font=("Malgun Gothic", 9),
                  bg="#222244", fg=SRT_GRAY,
                  relief="flat", cursor="hand2",
                  command=self.quit_app).pack(fill="x", padx=16, pady=(0, 8))

        self._log("SRT 매크로 준비 완료.  b1~b5 이미지를 캡처 후 시작하세요.")

        # 하단 크레딧 (빨간 둥근 테두리)
        cv_w, cv_h, r = 300, 34, 10
        ooo_frame = tk.Frame(self.root, bg=SRT_DARK)
        ooo_frame.pack(pady=(4, 8))
        ooo_cv = tk.Canvas(ooo_frame, width=cv_w, height=cv_h,
                           bg=SRT_DARK, highlightthickness=0)
        ooo_cv.pack()
        self._draw_rounded_rect_outline(ooo_cv, 2, 2, cv_w-3, cv_h-3,
                                        r, outline=SRT_RED, width=3)
        ooo_cv.create_text(cv_w // 2, cv_h // 2,
                           text="Developed by HSM of Orc Holdings.",
                           fill="white", font=("Malgun Gothic", 10, "bold"))

    # ── 미리보기 (썸네일) ───────────────────────────────────────
    def _draw_preview(self, prefix):
        cv = self._preview_canvas.get(prefix)
        if cv is None:
            return
        cv.delete("all")
        path = find_image_file(prefix)
        if path:
            try:
                img = Image.open(path)
                img.thumbnail((PREV_W, PREV_H), Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                self._preview_photo[prefix] = photo
                cv.create_image(PREV_W // 2, PREV_H // 2,
                                anchor="center", image=photo)
                return
            except Exception:
                pass
        cv.create_text(PREV_W // 2, PREV_H // 2 - 6,
                       text=prefix, fill=SRT_GRAY,
                       font=("Malgun Gothic", 9, "bold"))
        cv.create_text(PREV_W // 2, PREV_H // 2 + 10,
                       text="캡처 전", fill="#555577",
                       font=("Malgun Gothic", 8))

    # ── 크게 보기 팝업 (클릭 시) ────────────────────────────────
    def _show_large_preview(self, prefix):
        num = prefix[1:]        # "b1" → "1"
        s_prefix = f"s{num}"   # "s1"
        win_title = s_prefix
        path = find_image_file(s_prefix)
        if not path:
            messagebox.showinfo("미리보기", f"{s_prefix} 이미지 파일이 없습니다.\n{s_prefix}.png 를 폴더에 넣어주세요.")
            return
        try:
            orig = Image.open(path)
        except Exception as e:
            messagebox.showerror("오류", f"이미지 로드 실패: {e}")
            return

        win = tk.Toplevel(self.root)
        win.title(win_title)
        win.attributes("-topmost", True)
        win.resizable(True, True)
        iw, ih = max(orig.width, 200), max(orig.height, 150)
        win.geometry(f"{iw}x{ih}")

        canvas = tk.Canvas(win, bg="black", highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        state = {"photo": None}

        def _redraw(event=None):
            w = canvas.winfo_width()
            h = canvas.winfo_height()
            if w < 2 or h < 2:
                return
            resized = orig.copy()
            resized.thumbnail((w, h), Image.LANCZOS)
            photo = ImageTk.PhotoImage(resized)
            state["photo"] = photo
            canvas.delete("all")
            canvas.create_image(w // 2, h // 2, anchor="center", image=photo)

        canvas.bind("<Configure>", _redraw)

    # ── 로그 / 상태 ─────────────────────────────────────────────
    def _log(self, msg):
        def _u():
            self.log_text.configure(state="normal")
            self.log_text.insert("end", f"> {msg}\n")
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
        self.root.after(0, _u)

    def _set_status(self, text, color=SRT_GREEN):
        def _u():
            self.status_var.set(text)
            self.status_label.configure(fg=color)
            self.log_text.configure(state="normal")
            self.log_text.insert("end", f"> {text}\n")
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
        self.root.after(0, _u)

    # ── 이미지 캡처 ─────────────────────────────────────────────
    def _capture_image(self, prefix):
        self.root.withdraw()
        self.root.after(150, lambda: self._do_capture(prefix))

    def _do_capture(self, prefix):
        sel = RegionSelector(self.root)
        self.root.wait_window(sel)
        if not sel.region:
            self.root.deiconify()
            self._log("캡처 취소됨.")
            return
        time.sleep(0.15)
        x, y, w, h = sel.region
        shot = pyautogui.screenshot(region=(x, y, w, h))
        self.root.deiconify()
        for old in glob.glob(os.path.join(BASE_DIR, f"{prefix}.*")):
            os.remove(old)
        dest = os.path.join(BASE_DIR, f"{prefix}.png")
        shot.save(dest)
        self.root.after(0, lambda: self._draw_preview(prefix))
        self._log(f"{prefix}.png 저장 완료.")

    # ── 사운드 ─────────────────────────────────────────────────
    def _play_sound_loop(self):
        s1 = os.path.join(BASE_DIR, "s1.mp3")
        if not os.path.exists(s1):
            self._set_status("s1.mp3 없음! 소리 없이 대기합니다.", SRT_GOLD)
            return
        pygame.mixer.music.load(s1)
        pygame.mixer.music.play(-1)

    def _stop_sound(self):
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass

    # ── 매크로 종료 ─────────────────────────────────────────────
    def stop_macro(self):
        self._macro_running = False
        self._stop_sound()
        self._set_status("매크로 종료됨.", SRT_GOLD)

    # ── 이미지 매칭 ─────────────────────────────────────────────
    def _match(self, template, region=None, threshold=0.78):
        if region:
            x, y, w, h = region
            shot = pyautogui.screenshot(region=(x, y, w, h))
            ox, oy = x, y
        else:
            shot = pyautogui.screenshot()
            ox, oy = 0, 0
        screen = cv2.cvtColor(np.array(shot), cv2.COLOR_RGB2BGR)
        try:
            wx = self.root.winfo_x();  wy = self.root.winfo_y()
            ww = self.root.winfo_width(); wh = self.root.winfo_height()
            sx1 = max(0, wx - ox);  sy1 = max(0, wy - oy)
            sx2 = min(screen.shape[1], wx - ox + ww)
            sy2 = min(screen.shape[0], wy - oy + wh)
            if sx2 > sx1 and sy2 > sy1:
                screen[sy1:sy2, sx1:sx2] = 0
        except Exception:
            pass
        th_h, th_w = template.shape[:2]
        if th_h > screen.shape[0] or th_w > screen.shape[1]:
            return None
        res = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
        _, val, _, loc = cv2.minMaxLoc(res)
        if val >= threshold:
            return (ox + loc[0] + th_w // 2, oy + loc[1] + th_h // 2)
        return None

    # ── 매크로 시작 ─────────────────────────────────────────────
    def start_seat_macro(self):
        if self._macro_running:
            messagebox.showinfo("알림", "매크로 실행 중입니다. F12로 먼저 종료하세요.")
            return
        missing = [p for p in ("b1", "b2", "b3", "b4", "b5")
                   if not find_image_file(p)]
        if missing:
            messagebox.showwarning("이미지 없음",
                f"필수 이미지 없음: {', '.join(missing)}\n먼저 캡처하세요.")
            return
        self.root.withdraw()
        self.root.after(150, self._open_selector)

    def _open_selector(self):
        sel = RegionSelector(self.root)
        self.root.wait_window(sel)
        self.root.deiconify()
        if sel.region:
            self._region = sel.region
            self._macro_running = True
            self._search_thread = threading.Thread(
                target=self._seat_loop, daemon=True)
            self._search_thread.start()
        else:
            self._log("범위 지정 취소됨.")

    # ── 템플릿 로드 ─────────────────────────────────────────────
    def _load(self, prefix):
        p = find_image_file(prefix)
        if not p:
            self._set_status(f"{prefix} 파일 없음!", SRT_RED)
            self._macro_running = False
            return None
        # cv2.imread는 한글 경로를 못 읽으므로 imdecode 사용
        img = cv2.imdecode(np.fromfile(p, dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            self._set_status(f"{prefix} 로드 실패! (경로 오류)", SRT_RED)
            self._macro_running = False
        return img

    # ── 성공 처리 ───────────────────────────────────────────────
    def _on_success(self):
        self._set_status("예매 성공! 알림음 5분 재생 중...", SRT_GREEN)
        self._play_sound_loop()
        deadline = time.time() + 300
        while self._macro_running and time.time() < deadline:
            time.sleep(0.5)
        self._stop_sound()
        self._macro_running = False
        self._set_status("알림음 종료.", SRT_GOLD)

    # ── 둥근 테두리 그리기 ──────────────────────────────────────
    def _draw_rounded_rect_outline(self, canvas, x1, y1, x2, y2, r, outline, width):
        canvas.create_line(x1+r, y1, x2-r, y1, fill=outline, width=width)
        canvas.create_line(x1+r, y2, x2-r, y2, fill=outline, width=width)
        canvas.create_line(x1, y1+r, x1, y2-r, fill=outline, width=width)
        canvas.create_line(x2, y1+r, x2, y2-r, fill=outline, width=width)
        canvas.create_arc(x1, y1, x1+2*r, y1+2*r, start=90,  extent=90,  style="arc", outline=outline, width=width)
        canvas.create_arc(x2-2*r, y1, x2, y1+2*r, start=0,   extent=90,  style="arc", outline=outline, width=width)
        canvas.create_arc(x1, y2-2*r, x1+2*r, y2, start=180, extent=90,  style="arc", outline=outline, width=width)
        canvas.create_arc(x2-2*r, y2-2*r, x2, y2, start=270, extent=90,  style="arc", outline=outline, width=width)

    def _scroll_top(self):
        pyautogui.hotkey("ctrl", "Home")
        time.sleep(0.5)

    # ────────────────────────────────────────────────────────────
    # SRT 매크로 알고리즘
    #   ① b2 탐색(전체화면) → 클릭(브라우저 포커스) + Ctrl+Home
    #   ② b1 탐색(전체화면) → 클릭  /  없으면 Ctrl+Home 후 재탐색
    #   ③ b2 탐색(전체화면) → 클릭  /  없으면 ①부터 재시작
    #   ④ b3 탐색(지정범위) → 클릭  /  없으면 ①부터 재시작
    #   ⑤ b5 탐색(전체화면) → 발견 시 클릭  /  없으면 ⑥으로 바로 이동
    #   ⑥ b4 탐색(전체화면) → 성공  /  없으면 ①부터 재시작
    # ────────────────────────────────────────────────────────────
    def _seat_loop(self):
        t1 = self._load("b1")
        t2 = self._load("b2")
        t3 = self._load("b3")
        t4 = self._load("b4")
        t5 = self._load("b5")
        if any(t is None for t in (t1, t2, t3, t4, t5)):
            return

        region = self._region

        while self._macro_running:

            # ① b2 탐색 → 클릭(브라우저 포커스) + Ctrl+Home
            self._set_status("브라우저 포커스: b2 탐색 중...")
            pos = self._match(t2)
            if pos:
                self._set_status("b2 발견 → 클릭 (브라우저 포커스 획득)")
                pyautogui.click(pos[0], pos[1])
                time.sleep(0.3)
            self._set_status("맨위 스크롤...")
            pyautogui.hotkey("ctrl", "Home")
            time.sleep(0.5)

            # ② b1 탐색 (전체화면)
            while self._macro_running:
                self._set_status("b1 이미지 탐색 중...")
                pos = self._match(t1)
                if pos:
                    self._set_status("b1 이미지 발견 → 클릭!")
                    pyautogui.click(pos[0], pos[1])
                    time.sleep(0.8)
                    break
                self._set_status("b1 이미지 없음 → 맨위 스크롤 후 재탐색")
                self._scroll_top()

            if not self._macro_running:
                break

            # ③ b2 탐색 (전체화면)
            self._set_status("b2 이미지 탐색 중...")
            pos = self._match(t2)
            if not pos:
                self._set_status("b2 이미지 없음 → 맨위로 재시작")
                self._scroll_top()
                continue
            self._set_status("b2 이미지 발견 → 클릭!")
            pyautogui.click(pos[0], pos[1])
            time.sleep(0.5)

            # ④ b3 탐색 (지정 범위만)
            self._set_status("b3 이미지 탐색 중... (지정 범위)")
            pos = self._match(t3, region)
            if not pos:
                self._set_status("b3 이미지 없음 → 맨위로 재시작")
                self._scroll_top()
                continue
            self._set_status("b3 이미지 발견 → 클릭!")
            pyautogui.click(pos[0], pos[1])
            time.sleep(0.5)

            # ⑤ b5 탐색 (전체화면) → 발견 시 클릭, 없으면 b4로 바로 이동
            self._set_status("b5 이미지 탐색 중...")
            pos = self._match(t5)
            if pos:
                self._set_status("b5 이미지 발견 → 클릭!")
                pyautogui.click(pos[0], pos[1])
                time.sleep(0.5)
            else:
                self._set_status("b5 이미지 없음 → b4 탐색으로 이동")

            # ⑥ b4 탐색 (전체화면, 최대 7초 반복)
            deadline = time.time() + 7
            found_b4 = False
            while self._macro_running and time.time() < deadline:
                self._set_status("b4 이미지 탐색 중... (최대 7초)")
                pos = self._match(t4)
                if pos:
                    found_b4 = True
                    break
                time.sleep(0.3)
            if found_b4:
                self._on_success()
                return

            self._set_status("b4 이미지 없음 → 맨위로 재시작")
            self._scroll_top()

        self._stop_sound()
        self._set_status("대기 중")

    # ── 종료 ────────────────────────────────────────────────────
    def quit_app(self):
        if messagebox.askyesno("종료", "SRT 매크로를 종료하시겠습니까?"):
            self._macro_running = False
            self._stop_sound()
            self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = SRTMacroApp(root)
    root.mainloop()
