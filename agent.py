import logging
import datetime
import os
from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    MetricsCollectedEvent,
    RoomInputOptions,
    WorkerOptions,
    cli,
    inference,
    metrics,
    function_tool,
    RunContext,
)
from livekit.plugins import noise_cancellation, silero

logger = logging.getLogger("agent")

load_dotenv(".env.local")
print("\n[DEBUG] Environment check:")
print("LIVEKIT_URL =", os.getenv("LIVEKIT_URL"))
print("LIVEKIT_API_KEY =", os.getenv("LIVEKIT_API_KEY"))
print("LIVEKIT_API_SECRET =", os.getenv("LIVEKIT_API_SECRET"))

class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions="""You are a highly intelligent, witty, medically helpful voice AI assistant named Vienna who is made by Avijit. The user is interacting with you via voice in Bengali language (বাংলা).
            You are curious, confident, and have a dry sense of humor. You speak naturally and clearly in Bengali, keeping your answers concise and conversational. Avoid complex formatting, punctuation, emojis, or symbols.
            Always respond in Bengali (বাংলা) to match the user's language. If the user asks something in English, you can respond in English, but prefer Bengali for Bengali-speaking users.
            If a request is unclear or outside your ability, you must pause, think aloud briefly, and ask a clarifying question before proceeding.
            You express reasoning in a human-like way without exposing raw logic or code—just short, natural explanations of your thought process.
            You maintain a sense of humor and personality in appropriate moments, using clever, dry remarks to keep conversations engaging but never sarcastic or rude.""",
        )

    # 🖥️ SYSTEM AUTOMATION & CONTROL ------------------------------------------
    
    @function_tool
    async def open_website(self, context: RunContext, url: str):
        """Open or navigate to a website.
        
        Args:
            url: The website URL to open (e.g., 'https://google.com')
        """
        logger.info(f"Opening website: {url}")
        return f"Opening {url}..."
    
    @function_tool
    async def search_web(self, context: RunContext, query: str):
        """Perform a quick web search.
        
        Args:
            query: The search query
        """
        logger.info(f"Searching web for: {query}")
        return f"Searching the web for '{query}'..."
    
    
    @function_tool
    async def get_datetime(self, context: RunContext):
        """Fetch current date and time."""
        now = datetime.datetime.now()
        return f"It's {now.strftime('%I:%M %p on %A, %B %d, %Y')}."
    
    
    @function_tool
    async def lookup_weather(self, context: RunContext, location: str):
        """Get real-time weather info.
        
        Args:
            location: City or location name
        """
        logger.info(f"Looking up weather for: {location}")
        return f"The weather in {location} is sunny, 27°C."
    
    @function_tool
    async def get_news(self, context: RunContext, topic: str):
        """Fetch trending or topic-specific news.
        
        Args:
            topic: News topic or category
        """
        logger.info(f"Fetching news about: {topic}")
        return f"Here are the latest headlines about {topic}."
    
    @function_tool
    async def get_stock_price(self, context: RunContext, symbol: str):
        """Retrieve stock or crypto prices.
        
        Args:
            symbol: Stock ticker symbol (e.g., 'AAPL', 'BTC')
        """
        logger.info(f"Getting stock price for: {symbol}")
        return f"{symbol.upper()} is currently trading at $188.40."
    
    
    
    @function_tool
    async def send_email(self, context: RunContext, to: str, subject: str, body: str):
        """Send an email.
        
        Args:
            to: Recipient email address
            subject: Email subject
            body: Email body content
        """
        logger.info(f"Sending email to {to} with subject: {subject}")
        return f"Email sent to {to} with subject '{subject}'."
    
    @function_tool
    async def read_emails(self, context: RunContext, count: int = 3):
        """Read a number of unread emails.
        
        Args:
            count: Number of emails to read
        """
        logger.info(f"Reading {count} emails")
        return f"You have {count} unread emails."

    
    @function_tool
    async def find_nearby_places(self, context: RunContext, place_type: str):
        """Find nearby restaurants, ATMs, etc.
        
        Args:
            place_type: Type of place (e.g., 'restaurants', 'ATMs', 'hospitals')
        """
        logger.info(f"Finding nearby {place_type}")
        return f"Found several nearby {place_type}s."
    


def prewarm(proc: JobProcess):
    """Prewarm function to load TurnDetector if available, else fallback to VAD."""
    try:
        # Try to import and load the new TurnDetector (for newer Silero versions)
        from livekit.plugins.silero import TurnDetector
        proc.userdata["turn_detector"] = TurnDetector.load()
        logger.info("✅ TurnDetector loaded successfully.")
    except Exception as e:
        # Fallback for older builds with optimized VAD settings
        from livekit.plugins import silero
        if hasattr(silero.VAD, "load"):
            # Configure VAD with more selective parameters to reduce background noise capture
            proc.userdata["vad"] = silero.VAD.load(
                activation_threshold=0.65,      # Higher threshold = requires clearer speech (default: 0.5)
                min_speech_duration=0.1,        # Minimum 100ms of speech to detect (filters short noise bursts)
                min_silence_duration=0.6,       # Wait 600ms of silence before ending turn (default: 0.55)
                prefix_padding_duration=0.3,    # Reduced padding to avoid capturing pre-speech noise
            )
            logger.info("✅ Silero VAD loaded with optimized settings (threshold: 0.65, min_speech: 0.1s)")
        else:
            proc.userdata["vad"] = silero.VAD()
        logger.warning(f"⚠️ TurnDetector unavailable, using Silero VAD instead: {e}")



async def entrypoint(ctx: JobContext):
    """Main entrypoint for the voice agent."""
    
    # Logging setup - add context fields for all log entries
    ctx.log_context_fields = {
        "room": ctx.room.name,
    }

    # Set up voice AI pipeline with STT, LLM, and TTS
    session = AgentSession(
        # Speech-to-text: Cartesia Ink-Whisper with Bengali language
        # Using LiveKit Inference - No Cartesia API key needed!
        stt=inference.STT(
            model="cartesia/ink-whisper", 
            language="bn"  # Bengali (বাংলা)
        ),
        
        # Large Language Model: GPT-4.1 Mini for fast responses
        llm=inference.LLM(model="openai/gpt-4.1-mini"),
        
        # Text-to-speech: Cartesia Sonic 3 with custom voice
        tts=inference.TTS(
            model="cartesia/sonic-3", 
            voice="1e22a4bb-6b86-4994-997a-0f309dc521d0"
        ),
        
        # VAD (Voice Activity Detection) for detecting when user is speaking
        vad=ctx.proc.userdata.get("turn_detector") or ctx.proc.userdata.get("vad"),
        # Allow LLM to generate response while waiting for end of turn
        preemptive_generation=True,
    )

    # Metrics collection for monitoring pipeline performance
    usage_collector = metrics.UsageCollector()

    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        """Log metrics when collected."""
        metrics.log_metrics(ev.metrics)
        usage_collector.collect(ev.metrics)

    async def log_usage():
        """Log usage summary on shutdown."""
        summary = usage_collector.get_summary()
        logger.info(f"Usage: {summary}")

    ctx.add_shutdown_callback(log_usage)

    # Start the session with Vienna assistant
    await session.start(
        agent=Assistant(),
        room=ctx.room,
        room_input_options=RoomInputOptions(
            # Background voice cancellation for cleaner audio
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    # Connect to the room
    await ctx.connect()


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))