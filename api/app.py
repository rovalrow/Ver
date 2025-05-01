from quart import Quart, request, jsonify, render_template
import os
import re
import aiohttp
import uuid
import json
import asyncio

app = Quart(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "0x4AAAAAABWfDQXfye-8ewXoXpq-SQj5iF0")

SCRIPTS_DIR = "scripts"
os.makedirs(SCRIPTS_DIR, exist_ok=True)

OBFUSCATOR_API_KEY = os.environ.get("OBFUSCATOR_API_KEY", "bf4f5e8e-291b-2a5f-dc7f-2b5fabdeab1eb69f")
NEW_SCRIPT_URL = "https://api.luaobfuscator.com/v1/obfuscator/newscript"
OBFUSCATE_URL = "https://api.luaobfuscator.com/v1/obfuscator/obfuscate"

def sanitize_filename(name):
    return re.sub(r"[^a-zA-Z0-9_-]", "", name)

def get_next_script_id():
    existing_files = [f.split(".")[0] for f in os.listdir(SCRIPTS_DIR) if f.endswith(".lua")]
    script_numbers = [int(f) for f in existing_files if f.isdigit()]
    return max(script_numbers, default=0) + 1

async def obfuscate_lua_code(code):
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"apikey": OBFUSCATOR_API_KEY, "content-type": "text"}
            async with session.post(NEW_SCRIPT_URL, headers=headers, data=code) as resp:
                session_data = await resp.json()
            
            if not session_data.get("sessionId"):
                return {"error": "Failed to create session"}, False

            session_id = session_data["sessionId"]
            obfuscate_headers = {
                "apikey": OBFUSCATOR_API_KEY,
                "sessionId": session_id,
                "content-type": "application/json"
            }
            options = {
                "MinifiyAll": True,
                "Virtualize": True,
                "Seed": str(uuid.uuid4().int)[:8],
                "CustomPlugins": {
                    "CachedEncryptStrings": True,
                    "CallRetAssignment": True,
                    "ControlFlowFlattenV2AllBlocks": True,
                    "DummyFunctionArgs": True,
                    "FuncChopper": True,
                    "Minifier2": True,
                    "WowPacker": True
                }
            }

            async with session.post(OBFUSCATE_URL, headers=obfuscate_headers, data=json.dumps(options)) as obf_resp:
                obf_data = await obf_resp.json()

            if not obf_data.get("code"):
                return {"error": "Failed to obfuscate code"}, False

            return {"obfuscated_code": obf_data["code"]}, True
    except Exception as e:
        return {"error": str(e)}, False

@app.route('/')
async def home():
    return await render_template("index.html")

@app.route('/generate', methods=['POST'])
async def generate():
    data = await request.get_json()
    script_content = data.get("script", "").strip()
    custom_name = sanitize_filename(data.get("name", "").strip())

    if not script_content:
        return jsonify({"error": "No script provided"}), 400

    obfuscation_result, success = await obfuscate_lua_code(script_content)
    if not success:
        return jsonify(obfuscation_result), 500

    obfuscated_script = obfuscation_result["obfuscated_code"]
    base_name = custom_name if custom_name else uuid.uuid4().hex
    script_name = base_name
    counter = 1
    while os.path.exists(os.path.join(SCRIPTS_DIR, f"{script_name}.lua")):
        script_name = f"{base_name}{counter}"
        counter += 1

    script_path = os.path.join(SCRIPTS_DIR, f"{script_name}.lua")
    async with asyncio.to_thread(open, script_path, "w", encoding="utf-8") as f:
        f.write(obfuscated_script)

    return jsonify({"link": f"/scriptguardian/files/scripts/loaders/{script_name}"}), 200

@app.route('/scriptguardian/files/scripts/loaders/<script_name>')
async def execute(script_name):
    script_path = os.path.join(SCRIPTS_DIR, f"{sanitize_filename(script_name)}.lua")

    if os.path.exists(script_path):
        user_agent = (request.headers.get("User-Agent") or "").lower()
        blocked_agents = ["curl/8.13.0", "wget/1.25.0", "httpie/3.2.4", "python-requests/2.32.3"]

        if any(ua == user_agent for ua in blocked_agents) or "termux" in user_agent:
            return await render_template("unauthorized.html"), 403

        if "roblox" in user_agent or "robloxapp" in user_agent:
            with open(script_path, "r", encoding="utf-8") as f:
                return f.read(), 200, {'Content-Type': 'text/plain'}

        return await render_template("unauthorized.html"), 403

    return 'game.Players.LocalPlayer:Kick("The script no longer exists. Please regenerate at scriptguardian.vercel.app")', 200, {'Content-Type': 'text/plain'}

@app.route('/api/obfuscate', methods=['POST'])
async def api_obfuscate():
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    data = await request.get_json()
    script_content = data.get("script", "")
    if not script_content:
        return jsonify({"error": "No script provided"}), 400

    obfuscation_result, success = await obfuscate_lua_code(script_content)
    if not success:
        return jsonify(obfuscation_result), 500

    return jsonify({"obfuscated_code": obfuscation_result["obfuscated_code"]}), 200
