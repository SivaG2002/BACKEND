import discord
from discord.ext import tasks
from discord import app_commands
from flask import Flask, request, jsonify
import threading
import firebase_admin
from firebase_admin import credentials, firestore
import asyncio

# ============ CONFIG =============
DISCORD_TOKEN = 'MTM5MzI5NTg2OTU5NTYxNTI0Mg.GQ4-P2.7m0ThA8tKHYLST_Rgt86jgdQTDNEV0p-rVKU7c'
GUILD_ID = 1393231094349959319
FIREBASE_KEY = 'firebase_key.json'
FLASK_PORT = 12762
FLASK_HOST = "0.0.0.0"
PUBLIC_BACKEND_URL = f"http://wintr.wisp.uno:{FLASK_PORT}"
# =================================

# Initialize Firebase
cred = credentials.Certificate(FIREBASE_KEY)
firebase_admin.initialize_app(cred)
db = firestore.client()

# Initialize Flask
flask_app = Flask(__name__)

# Store user state
active_users = {}  # user_id: (discord_user, asyncio.Future)

@flask_app.route('/api/score', methods=['POST'])
def receive_score():
    data = request.json
    user_id = data.get("user_id")
    username = data.get("username")
    score = data.get("score")

    if not (user_id and score):
        return jsonify({"error": "Missing fields"}), 400

    db.collection("quiz_scores").document(user_id).set({
        "name": username,
        "score": score
    })

    entry = active_users.pop(user_id, None)
    if entry:
        user, future = entry
        if not future.done():
            future.set_result((username, score))

    return jsonify({"status": "Score received"}), 200

# Initialize Discord
intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

@client.event
async def on_ready():
    await tree.sync(guild=discord.Object(id=GUILD_ID))
    print(f"✅ Bot is ready as {client.user}")
    print(f"🌐 Backend ready at: {PUBLIC_BACKEND_URL}/api/score")

@tree.command(name="play", description="Start the quiz", guild=discord.Object(id=GUILD_ID))
async def play(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    user_name = interaction.user.name

    await interaction.response.defer(thinking=True)

    future = asyncio.get_event_loop().create_future()
    active_users[user_id] = (interaction.user, future)

    quiz_url = f"https://quiz-olive-beta.vercel.app/?user={user_name}&id={user_id}"
    await interaction.followup.send(
        f"🧠 Start your quiz here: {quiz_url}\nI’ll wait for your score submission..."
    )

    try:
        username, score = await asyncio.wait_for(future, timeout=300)
        await interaction.followup.send(
            f"🎉 {username}, your score is **{score}**! Saved to Firebase."
        )
    except asyncio.TimeoutError:
        await interaction.followup.send(
            f"⌛ Timed out waiting for your score, {user_name}. Please try again later."
        )

def run_flask():
    flask_app.run(host=FLASK_HOST, port=FLASK_PORT)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    client.run(DISCORD_TOKEN)
