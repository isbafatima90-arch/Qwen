# Discord Voice-to-Text Bot with DeepSeek AI

A Discord bot that listens to voice channels, transcribes speech using AssemblyAI Universal-3 Pro, and responds using DeepSeek AI.

## Features

- 🎤 **Voice Transcription**: Real-time speech-to-text using AssemblyAI Universal-3 Pro
- 🤖 **AI Responses**: Intelligent responses powered by DeepSeek API
- 💬 **Conversation History**: Maintains context across messages
- 🔧 **Configurable**: Easy setup with environment variables

## Commands

### Text Commands
- `!ask <question>` - Ask DeepSeek a question
- `!clear` - Clear conversation history
- `!model <name>` - Change DeepSeek model
- `!help` - Show help message

### Voice Commands
- `!startvoice` - Start listening to voice channel
- `!stopvoice` - Stop voice recording
- `!voicehelp` - Show voice commands help

## Setup

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Copy `.env.example` to `.env` and fill in your values:

```env
# Discord Bot Configuration
DISCORD_BOT_TOKEN=your_discord_bot_token

# DeepSeek API Configuration
DEEPSEEK_API_KEY=your_deepseek_api_key
DEEPSEEK_API_URL=https://api.deepseek.com/v1/chat/completions
DEEPSEEK_MODEL=deepseek-chat

# AssemblyAI Configuration
ASSEMBLYAI_API_KEY=your_assemblyai_api_key

# Voice Channel Configuration (Get these from Discord)
GENERAL_VOICE_CHANNEL_ID=your_voice_channel_id
GENERAL_TEXT_CHANNEL_ID=your_text_channel_id
```

### 3. Get Channel IDs

1. Enable Developer Mode in Discord (User Settings → Advanced → Developer Mode)
2. Right-click your voice channel → Copy ID
3. Right-click your text channel → Copy ID
4. Paste into `.env` file

### 4. Run the Bot
```bash
python bot.py
```

## How It Works

1. Use `!startvoice` command to begin listening
2. Speak in the configured voice channel
3. Audio is streamed to AssemblyAI Universal-3 Pro for transcription
4. Transcriptions appear in the text channel with 🎤 emoji
5. DeepSeek automatically responds to transcriptions
6. Use `!stopvoice` to stop recording

## AssemblyAI Configuration

The bot uses AssemblyAI's Universal-3 Pro Streaming model with optimal settings:
- Model: `u3-rt-pro`
- Sample Rate: 16kHz
- Turn Detection: Punctuation-based
- min_turn_silence: 100ms
- max_turn_silence: 1000ms

## Security Notes

⚠️ **Never commit your `.env` file!** It contains sensitive API keys.

⚠️ **Regenerate exposed keys immediately** if they were accidentally shared.

## Requirements

- Python 3.8+
- Discord Bot Token
- DeepSeek API Key
- AssemblyAI API Key
- Voice and Text Channel IDs

## License

MIT
