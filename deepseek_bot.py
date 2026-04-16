import discord
from discord.ext import commands
import requests
import json
import os
from dotenv import load_dotenv
import asyncio
import websockets
import base64
import io
import wave
import struct

# Load environment variables
load_dotenv()

# Bot setup with correct intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    help_command=None,
)

# DeepSeek API configuration
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# AssemblyAI configuration
ASSEMBLYAI_API_KEY = os.getenv("ASSEMBLYAI_API_KEY")
GENERAL_VOICE_CHANNEL_ID = os.getenv("GENERAL_VOICE_CHANNEL_ID")
GENERAL_TEXT_CHANNEL_ID = os.getenv("GENERAL_TEXT_CHANNEL_ID")

# Voice recording state
voice_recording_active = False
current_voice_channel = None
audio_queue = asyncio.Queue()
assemblyai_ws = None
transcript_buffer = ""


class VoiceRecorder:
    """Handle voice recording and AssemblyAI streaming"""
    
    def __init__(self, bot_instance, text_channel_id):
        self.bot = bot_instance
        self.text_channel_id = text_channel_id
        self.is_recording = False
        self.audio_queue = asyncio.Queue()
        self.ws = None
        self.current_transcript = ""
        self.last_final_transcript = ""
        
    async def start_recording(self, voice_channel):
        """Start recording from voice channel"""
        if not ASSEMBLYAI_API_KEY:
            print("AssemblyAI API key not configured")
            return False
            
        self.is_recording = True
        try:
            # Connect to voice channel
            voice_client = await voice_channel.connect()
            
            # Connect to AssemblyAI WebSocket
            ws_url = f"wss://api.assemblyai.com/v2/realtime/ws?sample_rate=16000"
            headers = {"Authorization": ASSEMBLYAI_API_KEY}
            self.ws = await websockets.connect(ws_url, extra_headers=headers)
            
            # Start audio processing task
            asyncio.create_task(self.process_audio(voice_client))
            asyncio.create_task(self.handle_transcripts())
            
            print(f"Started recording in {voice_channel.name}")
            return True
        except Exception as e:
            print(f"Error starting recording: {e}")
            self.is_recording = False
            return False
    
    async def process_audio(self, voice_client):
        """Process audio from voice channel and send to AssemblyAI"""
        import pyaudio
        import numpy as np
        
        while self.is_recording and voice_client.is_connected():
            try:
                # Receive audio packet from Discord (48kHz, 16-bit, stereo)
                audio_packet = await asyncio.wait_for(
                    voice_client.receive(), timeout=1.0
                )
                
                if audio_packet and self.ws:
                    # Convert to bytes if needed
                    if hasattr(audio_packet, 'data'):
                        audio_data = audio_packet.data
                    else:
                        audio_data = audio_packet
                    
                    # Resample from 48kHz to 16kHz for AssemblyAI
                    # Simple decimation (every 3rd sample)
                    audio_array = np.frombuffer(audio_data, dtype=np.int16)
                    if len(audio_array) > 0:
                        resampled = audio_array[::3].tobytes()
                        
                        # Send to AssemblyAI as base64
                        audio_b64 = base64.b64encode(resampled).decode('utf-8')
                        await self.ws.send(json.dumps({
                            "audio_data": audio_b64
                        }))
                        
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                print(f"Audio processing error: {e}")
                await asyncio.sleep(0.1)
    
    async def handle_transcripts(self):
        """Handle incoming transcripts from AssemblyAI"""
        text_channel = self.bot.get_channel(int(self.text_channel_id))
        
        while self.is_recording and self.ws:
            try:
                response = await asyncio.wait_for(self.ws.recv(), timeout=1.0)
                data = json.loads(response)
                
                msg_type = data.get('message_type', '')
                transcript = data.get('text', '')
                
                if msg_type == 'FinalTranscript' and transcript:
                    self.last_final_transcript = transcript
                    if text_channel:
                        # Post transcription to text channel
                        await text_channel.send(f"🎤 **Heard:** {transcript}")
                        print(f"Transcription sent: {transcript}")
                        
                elif msg_type == 'PartialTranscript' and transcript:
                    self.current_transcript = transcript
                    
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                print(f"Transcript handling error: {e}")
                await asyncio.sleep(0.1)
    
    async def stop_recording(self):
        """Stop recording and cleanup"""
        self.is_recording = False
        
        # Close WebSocket
        if self.ws:
            await self.ws.close()
            self.ws = None
        
        # Disconnect from voice
        for vc in self.bot.voice_clients:
            if vc.is_connected():
                await vc.disconnect()
        
        print("Stopped recording")


# Global voice recorder instance
voice_recorder = None


async def call_deepseek_api(message_content, conversation_history=None):
    """
    Call DeepSeek API with the given message and conversation history
    """
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }

    messages = []

    if conversation_history:
        messages.extend(conversation_history)

    messages.append({"role": "user", "content": message_content})

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 2000,
    }

    try:
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload)
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except requests.exceptions.RequestException as e:
        print(f"API Request Error: {e}")
        return "Sorry, I encountered an error while contacting DeepSeek API."
    except (KeyError, IndexError) as e:
        print(f"API Response Parsing Error: {e}")
        return "Sorry, I had trouble understanding the response from DeepSeek."


conversation_histories = {}


def update_conversation_history(channel_id, user_message, assistant_response):
    if channel_id not in conversation_histories:
        conversation_histories[channel_id] = []
    conversation_histories[channel_id].extend([
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": assistant_response},
    ])
    if len(conversation_histories[channel_id]) > 20:
        conversation_histories[channel_id] = conversation_histories[channel_id][-20:]


@bot.event
async def on_ready():
    print(f"{bot.user} has connected to Discord!")
    await bot.change_presence(activity=discord.Game(name="!help for commands"))


@bot.command(name="ask")
async def ask_deepseek(ctx, *, question):
    async with ctx.typing():
        history = conversation_histories.get(ctx.channel.id, [])
        response = await call_deepseek_api(question, history)
        update_conversation_history(ctx.channel.id, question, response)
        if len(response) > 2000:
            chunks = [response[i:i+2000] for i in range(0, len(response), 2000)]
            for chunk in chunks:
                await ctx.send(chunk)
        else:
            await ctx.send(response)


@bot.command(name="clear")
async def clear_history(ctx):
    if ctx.channel.id in conversation_histories:
        del conversation_histories[ctx.channel.id]
        await ctx.send("Conversation history cleared!")
    else:
        await ctx.send("No conversation history to clear.")


@bot.command(name="model")
async def set_model(ctx, model_name):
    global DEEPSEEK_MODEL
    DEEPSEEK_MODEL = model_name
    await ctx.send(f"Model set to: {model_name}")


@bot.command(name="help")
async def bot_help(ctx):
    help_text = """
**DeepSeek Discord Bot Commands:**
`!ask <question>` - Ask DeepSeek a question
`!clear` - Clear conversation history for this channel
`!model <model_name>` - Change the DeepSeek model
`!startvoice` - Start listening to voice channel
`!stopvoice` - Stop voice recording
`!voicehelp` - Show voice commands help
`!help` - Show this help message

**Example:** `!ask What is artificial intelligence?`
"""
    await ctx.send(help_text)


@bot.command(name="startvoice")
async def start_voice(ctx):
    """Start voice recording in general voice channel"""
    global voice_recorder
    
    if not GENERAL_VOICE_CHANNEL_ID or not GENERAL_TEXT_CHANNEL_ID:
        await ctx.send("❌ Voice channels not configured. Set GENERAL_VOICE_CHANNEL_ID and GENERAL_TEXT_CHANNEL_ID in .env")
        return
    
    if voice_recorder and voice_recorder.is_recording:
        await ctx.send("🎤 Already recording!")
        return
    
    # Get voice channel
    voice_channel = ctx.bot.get_channel(int(GENERAL_VOICE_CHANNEL_ID))
    if not voice_channel:
        await ctx.send("❌ Voice channel not found!")
        return
    
    # Create voice recorder
    voice_recorder = VoiceRecorder(ctx.bot, GENERAL_TEXT_CHANNEL_ID)
    
    # Start recording
    success = await voice_recorder.start_recording(voice_channel)
    
    if success:
        await ctx.send("✅ Started listening to voice channel! Speak and I'll transcribe.")
    else:
        await ctx.send("❌ Failed to start voice recording.")


@bot.command(name="stopvoice")
async def stop_voice(ctx):
    """Stop voice recording"""
    global voice_recorder
    
    if not voice_recorder or not voice_recorder.is_recording:
        await ctx.send("🔇 Not currently recording.")
        return
    
    await voice_recorder.stop_recording()
    await ctx.send("⏹️ Stopped voice recording.")


@bot.command(name="voicehelp")
async def voice_help(ctx):
    """Show voice commands help"""
    help_text = """
**Voice Commands:**
`!startvoice` - Start listening to the configured voice channel
`!stopvoice` - Stop voice recording
`!voicehelp` - Show this help

**How it works:**
1. Use `!startvoice` to begin listening
2. Speak in the configured voice channel
3. Your speech is transcribed using AssemblyAI Universal-3 Pro
4. Transcriptions appear in the text channel
5. DeepSeek automatically responds to transcriptions
"""
    await ctx.send(help_text)


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    if message.content.startswith("!"):
        await bot.process_commands(message)
        return
    async with message.channel.typing():
        history = conversation_histories.get(message.channel.id, [])
        response = await call_deepseek_api(message.content, history)
        update_conversation_history(message.channel.id, message.content, response)
        if len(response) > 2000:
            chunks = [response[i:i+2000] for i in range(0, len(response), 2000)]
            for chunk in chunks:
                await message.channel.send(chunk)
        else:
            await message.channel.send(response)


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Please provide a question after the command. Example: `!ask What is AI?`")
    else:
        await ctx.send(f"An error occurred: {error}")


if __name__ == "__main__":
    bot_token = os.getenv("DISCORD_BOT_TOKEN")
    if not bot_token:
        print("Error: DISCORD_BOT_TOKEN not found in environment variables")
    else:
        bot.run(bot_token)
