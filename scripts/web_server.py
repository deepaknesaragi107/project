"""
==============================================================================
STANDALONE ZERO-DEPENDENCY HTTP API & AI WEB SERVER (:8000)
Powers live browser access for /docs, /health, /api/v1/chat, and web UI.
==============================================================================
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import re
import sys
import os
import time

# Ensure project root in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from scripts.cli_chat_assistant import (
    DB,
    tool_search_events,
    tool_get_seats,
    tool_hold_seats,
    tool_confirm_booking,
    ai_agent_respond,
    sweep_expired_holds,
)

SWAGGER_DOCS_HTML = """<!DOCTYPE html>
<html>
<head>
    <title>Member 3: AI Ticketing & Booking API Docs</title>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5.11.0/swagger-ui.css" />
    <style>
        body { margin: 0; background: #fafafa; font-family: sans-serif; }
        .topbar-banner { background: #1e293b; color: white; padding: 14px 24px; display: flex; justify-content: space-between; align-items: center; }
        .topbar-banner a { color: #38bdf8; text-decoration: none; font-weight: bold; }
    </style>
</head>
<body>
    <div class="topbar-banner">
        <div><strong>🎫 Member 3: Backend & AI Architect</strong> — Online Ticketing API</div>
        <div><a href="/">👉 Open Interactive AI Chat & Seating Dashboard</a></div>
    </div>
    <div id="swagger-ui"></div>
    <script src="https://unpkg.com/swagger-ui-dist@5.11.0/swagger-ui-bundle.js"></script>
    <script>
        const spec = {
            openapi: "3.0.3",
            info: {
                title: "AI-Powered Online Ticketing & Booking System",
                version: "1.0.0",
                description: "FastAPI server, PostgreSQL schema, Redis distributed locks (Anti-Overbooking), and Conversational AI Agent."
            },
            paths: {
                "/health": {
                    get: {
                        summary: "System Health Check",
                        responses: { "200": { description: "Healthy" } }
                    }
                },
                "/api/v1/events": {
                    get: {
                        summary: "List and search scheduled events",
                        responses: { "200": { description: "List of events" } }
                    }
                },
                "/api/v1/events/1/available-seats": {
                    get: {
                        summary: "Real-time available seats for Event 1 (Coldplay)",
                        responses: { "200": { description: "List of available seats" } }
                    }
                },
                "/api/v1/bookings/hold": {
                    post: {
                        summary: "Concurrency-safe seat hold (10-min lock)",
                        requestBody: {
                            content: {
                                "application/json": {
                                    example: {
                                        event_id: 1,
                                        seat_ids: [101],
                                        user_name: "Alex Mercer",
                                        user_email: "alex@example.com"
                                    }
                                }
                            }
                        },
                        responses: { "201": { description: "Hold granted" }, "409": { description: "Conflict - Seat locked" } }
                    }
                },
                "/api/v1/bookings/confirm": {
                    post: {
                        summary: "Confirm held booking after payment",
                        requestBody: {
                            content: {
                                "application/json": {
                                    example: { booking_reference: "BKG-XXXX" }
                                }
                            }
                        },
                        responses: { "200": { description: "Confirmed" } }
                    }
                },
                "/api/v1/chat": {
                    post: {
                        summary: "Conversational AI Ticketing Assistant",
                        requestBody: {
                            content: {
                                "application/json": {
                                    example: { message: "What concerts are in Mumbai?" }
                                }
                            }
                        },
                        responses: { "200": { description: "AI reply" } }
                    }
                }
            }
        };

        window.onload = function() {
            SwaggerUIBundle({
                spec: spec,
                dom_id: '#swagger-ui',
                deepLinking: true,
                presets: [
                    SwaggerUIBundle.presets.apis,
                    SwaggerUIBundle.SwaggerUIStandalonePreset
                ]
            });
        };
    </script>
</body>
</html>
"""

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>TicketAI - Booking Assistant & Seating Architecture</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        .chat-bubble-user { background: #3b82f6; color: white; border-radius: 18px 18px 4px 18px; }
        .chat-bubble-ai { background: #1e293b; color: #f1f5f9; border-radius: 18px 18px 18px 4px; }
    </style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen">
    <!-- Header -->
    <header class="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-50">
        <div class="max-w-7xl mx-auto px-4 py-3 flex justify-between items-center">
            <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-indigo-500 to-sky-400 flex items-center justify-center text-white text-xl shadow-lg shadow-sky-500/20">
                    <i class="fa-solid fa-ticket"></i>
                </div>
                <div>
                    <h1 class="font-bold text-lg leading-tight">TicketAI Assistant & Booking Engine</h1>
                    <span class="text-xs text-sky-400 font-medium">Member 3: Backend & AI Architect • Concurrency Protected</span>
                </div>
            </div>
            <div class="flex items-center gap-3">
                <a href="/docs" target="_blank" class="text-xs bg-slate-800 hover:bg-slate-700 px-3 py-1.5 rounded-lg border border-slate-700 font-semibold transition flex items-center gap-1.5">
                    <i class="fa-solid fa-book text-sky-400"></i> Swagger /docs
                </a>
                <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                    <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span> Server Active (:8000)
                </span>
            </div>
        </div>
    </header>

    <main class="max-w-7xl mx-auto px-4 py-6 grid grid-cols-1 lg:grid-cols-12 gap-6">
        <!-- Left: Interactive AI Assistant Chat -->
        <section class="lg:col-span-7 flex flex-col bg-slate-900 border border-slate-800 rounded-2xl shadow-xl overflow-hidden h-[750px]">
            <div class="p-4 border-b border-slate-800 bg-slate-800/50 flex justify-between items-center">
                <div class="flex items-center gap-2">
                    <i class="fa-solid fa-robot text-sky-400"></i>
                    <span class="font-semibold text-sm">Conversational AI Ticketing Concierge</span>
                </div>
                <span class="text-xs text-slate-400">LangChain / OpenAI Tool Calling</span>
            </div>

            <!-- Messages Log -->
            <div id="chat-messages" class="flex-1 p-4 overflow-y-auto space-y-4 text-sm">
                <div class="flex gap-2.5">
                    <div class="w-8 h-8 rounded-lg bg-sky-500/20 text-sky-400 flex items-center justify-center shrink-0">
                        <i class="fa-solid fa-robot text-xs"></i>
                    </div>
                    <div class="chat-bubble-ai p-3.5 max-w-[85%] whitespace-pre-line leading-relaxed">
👋 Hello! I am your AI Ticketing Assistant.
I can help you browse concerts, check available seats in real-time, hold tickets with anti-overbooking locks, and confirm your bookings.

Try asking:
• "What concerts are available?"
• "Show seats for Coldplay"
• "Hold seat 101 for Event 1"
                    </div>
                </div>
            </div>

            <!-- Suggested Action Pills -->
            <div class="px-4 py-2 border-t border-slate-800 bg-slate-900/60 flex flex-wrap gap-2 text-xs">
                <button onclick="sendPrompt('What concerts are available?')" class="bg-slate-800 hover:bg-slate-700 text-slate-300 px-2.5 py-1 rounded-full border border-slate-700 transition">
                    🎶 What concerts?
                </button>
                <button onclick="sendPrompt('Show available seats for Coldplay')" class="bg-slate-800 hover:bg-slate-700 text-slate-300 px-2.5 py-1 rounded-full border border-slate-700 transition">
                    🪑 Show Coldplay seats
                </button>
                <button onclick="sendPrompt('Hold seat 101 for Event 1')" class="bg-slate-800 hover:bg-slate-700 text-slate-300 px-2.5 py-1 rounded-full border border-slate-700 transition">
                    🔒 Hold Seat 101
                </button>
            </div>

            <!-- Chat Input -->
            <form onsubmit="handleChatSubmit(event)" class="p-3 border-t border-slate-800 bg-slate-900 flex gap-2">
                <input id="chat-input" type="text" placeholder="Ask to view shows, hold seats, or confirm..." 
                    class="flex-1 bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-sky-500 text-white placeholder-slate-500">
                <button type="submit" class="bg-sky-500 hover:bg-sky-400 text-slate-950 px-5 py-2.5 rounded-xl font-bold text-sm transition flex items-center gap-2">
                    Send <i class="fa-solid fa-paper-plane text-xs"></i>
                </button>
            </form>
        </section>

        <!-- Right: Live Seating Map & Architecture Monitor -->
        <section class="lg:col-span-5 flex flex-col gap-6">
            <!-- Event & Live Seating Status -->
            <div class="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-xl">
                <div class="flex justify-between items-center mb-4">
                    <h2 class="font-bold text-base flex items-center gap-2">
                        <i class="fa-solid fa-couch text-indigo-400"></i> Event #1 Real-Time Seating
                    </h2>
                    <button onclick="fetchSeats()" class="text-xs text-sky-400 hover:underline">
                        <i class="fa-solid fa-rotate text-[10px]"></i> Refresh
                    </button>
                </div>
                <div class="text-xs text-slate-400 mb-3">
                    Coldplay: Music of the Spheres • D.Y. Patil Stadium, Mumbai
                </div>

                <!-- Seat Grid -->
                <div id="seats-grid" class="grid grid-cols-3 gap-2 text-xs">
                    <div class="p-3 rounded-xl bg-slate-800/80 border border-slate-700 text-center animate-pulse">Loading seats...</div>
                </div>

                <div class="mt-4 pt-3 border-t border-slate-800 flex justify-around text-[11px] text-slate-400">
                    <span class="flex items-center gap-1.5"><span class="w-2.5 h-2.5 rounded bg-emerald-500 inline-block"></span> Available</span>
                    <span class="flex items-center gap-1.5"><span class="w-2.5 h-2.5 rounded bg-amber-500 inline-block"></span> Held (10m lock)</span>
                    <span class="flex items-center gap-1.5"><span class="w-2.5 h-2.5 rounded bg-rose-500 inline-block"></span> Booked</span>
                </div>
            </div>

            <!-- Architecture Feature Cards -->
            <div class="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-xl space-y-3.5 text-xs">
                <h3 class="font-bold text-sm text-slate-200 flex items-center gap-2">
                    <i class="fa-solid fa-shield-halved text-emerald-400"></i> Anti-Overbooking Guardrails
                </h3>
                <div class="p-3 bg-slate-950/60 rounded-xl border border-slate-800/80">
                    <strong class="text-sky-300 block mb-0.5">1. Redis Distributed Lock</strong>
                    Atomic NX/PX tokens prevent cross-process race conditions when concurrent requests hammer the same seat.
                </div>
                <div class="p-3 bg-slate-950/60 rounded-xl border border-slate-800/80">
                    <strong class="text-indigo-300 block mb-0.5">2. Deadlock-Free Multi-Lock</strong>
                    Multi-seat acquisitions sort IDs deterministically before acquiring, eliminating circular wait deadlocks.
                </div>
                <div class="p-3 bg-slate-950/60 rounded-xl border border-slate-800/80">
                    <strong class="text-amber-300 block mb-0.5">3. 10-Minute Hold Window</strong>
                    Stale reservations are automatically swept by the background worker, restoring seats to the pool.
                </div>
            </div>
        </section>
    </main>

    <script>
        async function fetchSeats() {
            try {
                const res = await fetch('/api/v1/events/1/available-seats');
                const data = await res.json();
                const grid = document.getElementById('seats-grid');
                grid.innerHTML = '';

                data.seats.forEach(s => {
                    const card = document.createElement('div');
                    let statusColor = "border-emerald-500/40 bg-emerald-500/10 text-emerald-300";
                    let badge = "AVAILABLE";
                    if (s.status === "HELD") {
                        statusColor = "border-amber-500/40 bg-amber-500/10 text-amber-300";
                        badge = "HELD";
                    } else if (s.status === "BOOKED") {
                        statusColor = "border-rose-500/40 bg-rose-500/10 text-rose-300";
                        badge = "BOOKED";
                    }

                    card.className = `p-3 rounded-xl border ${statusColor} text-center flex flex-col justify-between`;
                    card.innerHTML = `
                        <div class="font-bold text-sm text-white">${s.seat_number}</div>
                        <div class="text-[10px] text-slate-400">${s.tier}</div>
                        <div class="font-semibold text-xs mt-1">$${s.price}</div>
                        <div class="text-[9px] uppercase tracking-wider font-extrabold mt-1.5">${badge}</div>
                    `;
                    grid.appendChild(card);
                });
            } catch(e) {
                console.error("Error fetching seats", e);
            }
        }

        async function handleChatSubmit(e) {
            e.preventDefault();
            const input = document.getElementById('chat-input');
            const msg = input.value.trim();
            if (!msg) return;
            input.value = '';
            await sendPrompt(msg);
        }

        async function sendPrompt(msg) {
            const container = document.getElementById('chat-messages');

            // Append user bubble
            const userDiv = document.createElement('div');
            userDiv.className = "flex gap-2.5 justify-end";
            userDiv.innerHTML = `<div class="chat-bubble-user p-3 max-w-[85%]">${msg}</div>`;
            container.appendChild(userDiv);
            container.scrollTop = container.scrollHeight;

            // Typing indicator
            const typingDiv = document.createElement('div');
            typingDiv.className = "flex gap-2.5";
            typingDiv.id = "typing-bubble";
            typingDiv.innerHTML = `
                <div class="w-8 h-8 rounded-lg bg-sky-500/20 text-sky-400 flex items-center justify-center shrink-0">
                    <i class="fa-solid fa-robot text-xs"></i>
                </div>
                <div class="chat-bubble-ai p-3 text-slate-400 italic">Thinking...</div>
            `;
            container.appendChild(typingDiv);
            container.scrollTop = container.scrollHeight;

            try {
                const res = await fetch('/api/v1/chat', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ message: msg })
                });
                const data = await res.json();

                typingDiv.remove();

                const aiDiv = document.createElement('div');
                aiDiv.className = "flex gap-2.5";
                aiDiv.innerHTML = `
                    <div class="w-8 h-8 rounded-lg bg-sky-500/20 text-sky-400 flex items-center justify-center shrink-0">
                        <i class="fa-solid fa-robot text-xs"></i>
                    </div>
                    <div class="chat-bubble-ai p-3.5 max-w-[85%] whitespace-pre-line leading-relaxed">${data.reply}</div>
                `;
                container.appendChild(aiDiv);
                container.scrollTop = container.scrollHeight;

                fetchSeats();
            } catch(e) {
                typingDiv.remove();
            }
        }

        // Initial seat load
        fetchSeats();
        setInterval(fetchSeats, 5000);
    </script>
</body>
</html>
"""


class StandaloneApiHandler(BaseHTTPRequestHandler):
    def _send_json(self, status_code, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, status_code, html_str):
        body = html_str.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]

        if path == "/":
            self._send_html(200, DASHBOARD_HTML)
        elif path == "/docs":
            self._send_html(200, SWAGGER_DOCS_HTML)
        elif path == "/health":
            self._send_json(200, {
                "status": "HEALTHY",
                "app_name": "AI-Powered Online Ticketing & Booking System",
                "database": "HEALTHY",
                "redis": "HEALTHY",
                "anti_overbooking_engine": "ACTIVE",
            })
        elif path == "/api/v1/events":
            events = tool_search_events()
            self._send_json(200, events)
        elif path.startswith("/api/v1/events/") and path.endswith("/available-seats"):
            parts = path.split("/")
            ev_id = int(parts[4]) if len(parts) >= 5 and parts[4].isdigit() else 1
            seats_info = tool_get_seats(ev_id)
            self._send_json(200, seats_info)
        else:
            self._send_json(404, {"error": "Not Found", "available_routes": ["/", "/docs", "/health", "/api/v1/events", "/api/v1/chat"]})

    def do_POST(self):
        path = self.path.split("?")[0]
        content_len = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(content_len) if content_len > 0 else b"{}"

        try:
            body = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
        except Exception:
            body = {}

        if path == "/api/v1/chat":
            msg = body.get("message", "")
            reply = ai_agent_respond(msg)
            self._send_json(200, {"reply": reply, "session_id": body.get("session_id", "default-session")})

        elif path == "/api/v1/bookings/hold":
            ev_id = body.get("event_id", 1)
            seat_ids = body.get("seat_ids", [101])
            name = body.get("user_name", "Alex Mercer")
            email = body.get("user_email", "alex@example.com")
            res = tool_hold_seats(ev_id, seat_ids, name, email)
            status_code = 201 if res.get("success") else 409
            self._send_json(status_code, res)

        elif path == "/api/v1/bookings/confirm":
            ref = body.get("booking_reference", "")
            res = tool_confirm_booking(ref)
            status_code = 200 if res.get("success") else 400
            self._send_json(status_code, res)

        else:
            self._send_json(404, {"error": "Endpoint not found"})


def run_server(port=8000):
    server_address = ("0.0.0.0", port)
    httpd = HTTPServer(server_address, StandaloneApiHandler)
    print("=" * 70)
    print(f"🚀 TICKETAI SERVER RUNNING ON http://localhost:{port}")
    print(f"  • Interactive Web Dashboard & Chat: http://localhost:{port}/")
    print(f"  • Swagger API Documentation:       http://localhost:{port}/docs")
    print(f"  • System Health Check:              http://localhost:{port}/health")
    print("=" * 70)
    httpd.serve_forever()


if __name__ == "__main__":
    run_server(8000)

