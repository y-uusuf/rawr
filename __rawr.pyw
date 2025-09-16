import sys
import subprocess
import importlib
import os
import re
import ctypes
import socket
import threading
import tkinter as tk
from tkinter import simpledialog, filedialog, scrolledtext, messagebox
import io
import base64
import time
import json


# --- Auto-install packages ---
def install_if_missing(package):
    try:
        importlib.import_module(package)
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])

install_if_missing("pillow")
from PIL import Image, ImageTk, ImageSequence
install_if_missing("requests")
import requests

# --- DPI Fix ---
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except:
    pass

# --- Config ---
IP_URL = "https://raw.githubusercontent.com/y-uusuf/rawr/refs/heads/main/ip.txt"
PORT = 5000
FONT_NAME = "Whitney", "Helvetica Neue", "Helvetica", "Arial", "sans-serif"
FONT_SIZE = 14
RETRY_INTERVAL = 15
RETRY_DURATION = 60
IMAGE_END_MARKER = b"<ENDIMAGE>"

# Discord-like colors
COLORS = {
    'bg_primary': '#36393f',
    'bg_secondary': '#2f3136',
    'bg_tertiary': '#202225',
    'text_normal': '#dcddde',
    'text_muted': '#72767d',
    'text_bright': '#ffffff',
    'accent': '#5865f2',
    'accent_hover': '#4752c4',
    'success': '#3ba55d',
    'warning': '#faa81a',
    'error': '#ed4245',
    'input_bg': '#40444b',
    'input_border': '#1e2124'
}

# --- Modern Tkinter Setup (root exists before dialog) ---
root = tk.Tk()
root.withdraw()
root.title("careful, you're being watched 0_0")
root.geometry("800x900")
root.configure(bg=COLORS['bg_secondary'])
root.tk.call("tk", "scaling", 1.0)
root.overrideredirect(False)


# --- Helper: modern button (must exist before get_username uses it) ---
def create_modern_button(parent, text, color, hover_color, command):
    btn = tk.Button(
        parent,
        text=text,
        bg=color,
        fg=COLORS['text_bright'],
        font=(FONT_NAME[0], FONT_SIZE, "bold"),
        relief='flat',
        bd=0,
        padx=20,
        pady=8,
        cursor='hand2',
        command=command
    )

    def on_enter(e):
        btn.config(bg=hover_color)
    def on_leave(e):
        btn.config(bg=color)

    btn.bind("<Enter>", on_enter)
    btn.bind("<Leave>", on_leave)
    return btn

# --- Username dialog (defined before use) ---
def get_username():
    dialog = tk.Toplevel(root)
    dialog.title("hey -//-")
    dialog.geometry("400x200")
    dialog.configure(bg=COLORS['bg_secondary'])
    dialog.resizable(False, False)
    dialog.grab_set()

    # Center the dialog
    dialog.update_idletasks()
    x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
    y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
    dialog.geometry(f"+{x}+{y}")

    tk.Label(dialog, text="what do you wanna be called?",
             bg=COLORS['bg_secondary'], fg=COLORS['text_bright'],
             font=(FONT_NAME[0], 16, "bold")).pack(pady=30)

    entry = tk.Entry(dialog, bg=COLORS['input_bg'], fg=COLORS['text_bright'],
                     font=(FONT_NAME[0], 14), relief='flat', bd=0,
                     highlightthickness=1, highlightcolor=COLORS['accent'])
    entry.pack(pady=10, padx=50, fill=tk.X, ipady=8)

    result = {"username": None}

    def on_ok():
        if entry.get().strip():
            result["username"] = entry.get().strip()
            dialog.destroy()

    ok_btn = create_modern_button(dialog, "join up.", COLORS['success'], "#2d7d43", on_ok)
    ok_btn.pack(pady=20)

    entry.bind("<Return>", lambda e: on_ok())
    entry.focus()

    root.wait_window(dialog)
    return result["username"]

# --- Prompt for username BEFORE building the main chat UI ---
username = None
while not username:
    username = get_username()
    if not username:
        root.quit()
        exit()
root.deiconify()

# --- Persistent references and state (defined early) ---
image_refs = []
label_refs = []
gif_refs = []
typing_users = {}
typing_lock = threading.Lock()

client = None
server_ip = None
connected = False
typing_status = False
last_typing_time = 0

animations = []

# --- Title bar (create after username so UI doesn't show until after join) ---
title_frame = tk.Frame(root, bg=COLORS['bg_tertiary'], height=30)
title_frame.pack(fill=tk.X)
title_frame.pack_propagate(False)

title_label = tk.Label(title_frame, text="🔒 Secure Chat",
                      bg=COLORS['bg_tertiary'], fg=COLORS['text_normal'],
                      font=(FONT_NAME[0], 12, "bold"))
title_label.pack(side=tk.LEFT, padx=15, pady=5)

# --- Main chat container (build after username) ---
main_frame = tk.Frame(root, bg=COLORS['bg_primary'])
main_frame.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)

messages_frame = scrolledtext.ScrolledText(
    main_frame,
    bg=COLORS['bg_primary'],
    fg=COLORS['text_normal'],
    state='disabled',
    wrap=tk.WORD,
    font=(FONT_NAME[0], FONT_SIZE),
    relief='flat',
    bd=0,
    highlightthickness=0,
    selectbackground=COLORS['accent'],
    insertbackground=COLORS['text_bright'],
    padx=20,
    pady=15
)
messages_frame.pack(padx=20, pady=(20, 10), fill=tk.BOTH, expand=True)

typing_label = tk.Label(
    main_frame,
    text="",
    bg=COLORS['bg_primary'],
    fg=COLORS['text_muted'],
    font=(FONT_NAME[0], 12, "italic"),
    anchor='w'
)
typing_label.pack(side=tk.BOTTOM, fill=tk.X, padx=25, pady=(0, 5))

input_frame = tk.Frame(main_frame, bg=COLORS['bg_primary'])
input_frame.pack(fill=tk.X, padx=20, pady=(5, 20))

input_field = tk.Entry(
    input_frame,
    bg=COLORS['input_bg'],
    fg=COLORS['text_bright'],
    insertbackground=COLORS['text_bright'],
    font=(FONT_NAME[0], FONT_SIZE),
    relief='flat',
    bd=0,
    highlightthickness=1,
    highlightcolor=COLORS['accent'],
    highlightbackground=COLORS['input_border']
)
input_field.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10), pady=5, ipady=8)

send_button = create_modern_button(input_frame, "Send", COLORS['accent'], COLORS['accent_hover'], None)
send_button.pack(side=tk.RIGHT, padx=(5, 0))

image_button = create_modern_button(input_frame, "🔎", COLORS['input_bg'], COLORS['bg_secondary'], None)
image_button.pack(side=tk.RIGHT, padx=(5, 0))

# --- Animation helpers ---
def animate_fade_in(widget, duration=300):
    steps = 20
    step_time = duration // steps
    alpha_step = 1.0 / steps

    def fade_step(current_alpha):
        if current_alpha <= 1.0:
            widget.update()
            root.after(step_time, lambda: fade_step(current_alpha + alpha_step))

    fade_step(0.0)

def animate_slide_in(widget, start_x, end_x, duration=200):
    steps = 15
    step_time = duration // steps
    x_step = (end_x - start_x) / steps

    def slide_step(current_x, step_count):
        if step_count < steps:
            widget.place(x=current_x)
            root.after(step_time, lambda: slide_step(current_x + x_step, step_count + 1))
        else:
            widget.place(x=end_x)

    widget.place(x=start_x)
    slide_step(start_x, 0)

# --- GUI Helpers ---
def add_message(msg, animate=True):
    messages_frame.configure(state='normal')

    timestamp = time.strftime("%H:%M")

    if ": " in msg and not msg.startswith("["):
        user, message = msg.split(": ", 1)
        messages_frame.insert(tk.END, f"{timestamp} ", ('timestamp',))
        messages_frame.insert(tk.END, f"{user}", ('username',))
        messages_frame.insert(tk.END, f": {message}\n", ('message',))
    else:
        messages_frame.insert(tk.END, f"{timestamp} {msg}\n", ('system',))

    messages_frame.configure(state='disabled')
    messages_frame.yview(tk.END)

    if animate:
        def smooth_scroll():
            messages_frame.yview_moveto(1.0)
        root.after(50, smooth_scroll)

messages_frame.tag_config('timestamp', foreground=COLORS['text_muted'], font=(FONT_NAME[0], 11))
messages_frame.tag_config('username', foreground=COLORS['accent'], font=(FONT_NAME[0], FONT_SIZE, 'bold'))
messages_frame.tag_config('message', foreground=COLORS['text_normal'])
messages_frame.tag_config('system', foreground=COLORS['text_muted'], font=(FONT_NAME[0], FONT_SIZE, 'italic'))

def add_image(user, img_bytes, is_gif=False):
    container = tk.Frame(messages_frame, bg=COLORS['bg_primary'])

    timestamp = time.strftime("%H:%M")
    header_frame = tk.Frame(container, bg=COLORS['bg_primary'])
    header_frame.pack(fill=tk.X, anchor='w', padx=5, pady=(10, 5))

    tk.Label(header_frame, text=timestamp, bg=COLORS['bg_primary'],
             fg=COLORS['text_muted'], font=(FONT_NAME[0], 11)).pack(side=tk.LEFT)
    tk.Label(header_frame, text=f" {user}", bg=COLORS['bg_primary'],
             fg=COLORS['accent'], font=(FONT_NAME[0], FONT_SIZE, "bold")).pack(side=tk.LEFT)

    if is_gif:
        img = Image.open(io.BytesIO(img_bytes))
        frames = [ImageTk.PhotoImage(frame.copy().convert('RGBA')) for frame in ImageSequence.Iterator(img)]
        label_img = tk.Label(container, bg=COLORS['bg_primary'], relief='flat', bd=0)
        label_img.pack(anchor='w', padx=5, pady=(0, 10))
        gif_refs.append((frames, label_img, 0))
        def animate():
            if gif_refs:
                f, lbl, idx = gif_refs[-1]
                try:
                    lbl.configure(image=f[idx])
                    idx = (idx + 1) % len(f)
                    gif_refs[-1] = (f, lbl, idx)
                    lbl.after(100, animate)
                except:
                    pass
        animate()
    else:
        img = Image.open(io.BytesIO(img_bytes))
        img.thumbnail((400, 300), Image.LANCZOS)
        photo = ImageTk.PhotoImage(img)
        label_img = tk.Label(container, image=photo, bg=COLORS['bg_primary'], relief='flat', bd=0)
        label_img.photo = photo
        label_img.pack(anchor='w', padx=5, pady=(0, 10))
        image_refs.append(photo)

    label_refs.append(label_img)
    messages_frame.configure(state='normal')
    messages_frame.window_create(tk.END, window=container)
    messages_frame.insert(tk.END, "\n")
    messages_frame.configure(state='disabled')
    messages_frame.yview(tk.END)

# --- Tenor GIF extraction & download ---
def extract_tenor_gif_url(tenor_url):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0'
        }
        response = requests.get(tenor_url, headers=headers, timeout=10)
        if response.status_code != 200:
            return None
        content = response.text
        patterns = [
            r'"url":"([^"]*\.gif[^"]*)"',
            r"'url':'([^']*\.gif[^']*)'",
            r'contentUrl.*?"([^"]*\.gif[^"]*)"',
            r'"gif":{"url":"([^"]*)"',
            r'"mediumgif":{"url":"([^"]*)"',
        ]
        for pattern in patterns:
            matches = re.findall(pattern, content)
            if matches:
                gif_url = matches[0].replace('\\/', '/')
                if '.gif' in gif_url and gif_url.startswith('http'):
                    return gif_url
        return None
    except Exception as e:
        print(f"Error extracting Tenor GIF: {e}")
        return None

def download_gif(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            return response.content
    except Exception as e:
        print(f"Error downloading GIF: {e}")
    return None

# --- Typing indicator ---
typing_dots_animation = 0

def format_typing(users_list):
    global typing_dots_animation
    typing_dots_animation = (typing_dots_animation + 1) % 4
    dots = "." * typing_dots_animation

    n = len(users_list)
    if n == 0:
        return ""
    elif n == 1:
        return f"{users_list[0]} is typing{dots}"
    elif n == 2:
        return f"{users_list[0]} and {users_list[1]} are typing{dots}"
    else:
        return f"{', '.join(users_list[:-1])}, and {users_list[-1]} are typing{dots}"

def update_typing_indicator():
    with typing_lock:
        current_time = time.time()
        expired_users = [user for user, last_time in typing_users.items()
                        if current_time - last_time > 3.0]
        for user in expired_users:
            del typing_users[user]

        active_users = list(typing_users.keys())
        typing_text = format_typing(active_users)
        typing_label.config(text=typing_text)

    root.after(500, update_typing_indicator)

def add_typing_user(user):
    with typing_lock:
        typing_users[user] = time.time()

def on_keypress(event):
    global typing_status, last_typing_time
    current_time = time.time()

    if not typing_status or current_time - last_typing_time > 2.0:
        typing_status = True
        last_typing_time = current_time
        send_typing_signal()

        def reset_typing():
            global typing_status
            typing_status = False
        root.after(3000, reset_typing)

input_field.bind("<KeyPress>", on_keypress)

def send_typing_signal():
    if connected and client:
        try:
            message = f"TYPING::{username}\n"
            client.sendall(message.encode('utf-8'))
        except:
            pass

# --- Sending ---
def send_text():
    global connected
    msg = input_field.get().strip()
    if msg and connected:
        if re.match(r'https?://(www\.)?tenor\.com/view/.+', msg):
            add_message(f"{username}: 🔄 Loading GIF...")

            def load_tenor_gif():
                gif_url = extract_tenor_gif_url(msg)
                if gif_url:
                    img_bytes = download_gif(gif_url)
                    if img_bytes:
                        try:
                            header = f"IMAGE::{username}::".encode('utf-8')
                            client.sendall(header + base64.b64encode(img_bytes) + IMAGE_END_MARKER)
                            root.after(0, lambda: add_image(username, img_bytes, is_gif=True))
                            return
                        except:
                            pass

                root.after(0, lambda: add_message(f"{username}: {msg}"))
                try:
                    data = f"TEXT::{username}::{msg}\n".encode('utf-8')
                    client.sendall(data)
                except:
                    pass

            threading.Thread(target=load_tenor_gif, daemon=True).start()
        else:
            data = f"TEXT::{username}::{msg}\n".encode('utf-8')
            try:
                client.sendall(data)
                add_message(f"{username}: {msg}")
            except:
                add_message("[Error] Could not send message")
    input_field.delete(0, tk.END)

def send_image():
    global connected
    if not connected:
        add_message("[Error] Not connected")
        return

    file_path = filedialog.askopenfilename(
        title="Select Image/GIF",
        filetypes=[("Images","*.png *.jpg *.jpeg *.bmp *.gif *.webp")]
    )
    if file_path:
        add_message(f"{username}: 📤 Uploading...")

        def upload_image():
            try:
                with open(file_path, "rb") as f:
                    img_bytes = f.read()
                is_gif = file_path.lower().endswith((".gif", ".webp"))
                img_b64 = base64.b64encode(img_bytes)
                header = f"IMAGE::{username}::".encode('utf-8')
                client.sendall(header + img_b64 + IMAGE_END_MARKER)
                root.after(0, lambda: add_image(username, img_bytes, is_gif=is_gif))
            except Exception as e:
                root.after(0, lambda: add_message(f"[Error] Could not send image: {e}"))

        threading.Thread(target=upload_image, daemon=True).start()

# --- Receiving ---
def receive_messages():
    global connected
    buffer = b""

    while connected:
        try:
            data = client.recv(4096)
            if not data:
                break
            buffer += data

            while b'\n' in buffer or IMAGE_END_MARKER in buffer:
                if buffer.startswith(b"IMAGE::") and IMAGE_END_MARKER in buffer:
                    end_index = buffer.find(IMAGE_END_MARKER)
                    image_data = buffer[:end_index]
                    buffer = buffer[end_index + len(IMAGE_END_MARKER):]

                    try:
                        parts = image_data.split(b"::", 2)
                        if len(parts) >= 3:
                            user = parts[1].decode('utf-8')
                            img_b64 = parts[2]
                            if user != username:
                                img_bytes = base64.b64decode(img_b64)
                                is_gif = img_bytes[:6] in [b'GIF87a', b'GIF89a'] or b'WEBP' in img_bytes[:12]
                                root.after(0, lambda u=user, b=img_bytes, g=is_gif: add_image(u, b, is_gif=g))
                    except Exception as e:
                        print(f"Error processing image: {e}")
                    continue

                if b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    line_str = line.decode('utf-8', errors='ignore')

                    if line_str.startswith("TEXT::"):
                        try:
                            parts = line_str.split("::", 2)
                            if len(parts) >= 3:
                                user, message = parts[1], parts[2]
                                root.after(0, lambda u=user, m=message: add_message(f"{u}: {m}"))
                        except Exception as e:
                            print(f"Error processing text: {e}")

                    elif line_str.startswith("TYPING::"):
                        try:
                            parts = line_str.split("::", 1)
                            if len(parts) >= 2:
                                user = parts[1]
                                if user != username:
                                    root.after(0, lambda u=user: add_typing_user(u))
                        except Exception as e:
                            print(f"Error processing typing: {e}")
                    
                    # Handle server messages (join/leave notifications)
                    elif line_str.startswith("[Server]"):
                        root.after(0, lambda msg=line_str: add_message(msg))
                    
                    # Handle any other plain text messages that don't have prefixes
                    else:
                        if line_str.strip():  # Only if not empty
                            root.after(0, lambda msg=line_str: add_message(msg))
                else:
                    break

        except Exception as e:
            print(f"Error in receive_messages: {e}")
            break

    connected = False
    root.after(0, lambda: add_message("[Disconnected] Trying to reconnect..."))

# --- Connection ---
def connect_to_server(ip, port):
    global client, connected
    if connected:
        return True
    try:
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect((ip, port))
        connected = True
        add_message(f"[Connected] to {ip}:{port}")
        
        # Send join notification to server
        join_message = f"USER_JOINED::{username}\n"
        client.sendall(join_message.encode('utf-8'))
        
        threading.Thread(target=receive_messages, daemon=True).start()
        return True
    except Exception as e:
        connected = False
        add_message(f"[Error] Could not connect to {ip}:{port}")
        return False

def fetch_ip_from_url():
    try:
        r = requests.get(IP_URL, timeout=5)
        if r.status_code == 200:
            return r.text.strip()
    except:
        pass
    return None

def connection_manager():
    global server_ip, connected
    while True:
        if not connected:
            server_ip = fetch_ip_from_url()
            if not server_ip:
                add_message("[Error] Could not fetch server IP from URL")
                time.sleep(15)
                continue

            start_time = time.time()
            while time.time() - start_time < RETRY_DURATION and not connected:
                if connect_to_server(server_ip, PORT):
                    break
                time.sleep(RETRY_INTERVAL)

            if not connected:
                add_message("[Retrying] Re-fetching IP from URL...")
                time.sleep(5)
        else:
            time.sleep(5)

# --- Bindings ---
send_button.config(command=send_text)
image_button.config(command=send_image)
input_field.bind("<Return>", lambda e: send_text())

# Handle window closing to send leave notification
def on_closing():
    global connected, client
    if connected and client:
        try:
            leave_message = f"USER_LEFT::{username}\n"
            client.sendall(leave_message.encode('utf-8'))
            client.close()
        except:
            pass
    root.destroy()

root.protocol("WM_DELETE_WINDOW", on_closing)

# --- Startup ---
add_message("welcome to a super duper secret chat ^_<")
add_message("make sure you don't get caught lol")

threading.Thread(target=connection_manager, daemon=True).start()
update_typing_indicator()
root.mainloop()
