from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Duffel Flights API — https://duffel.com/docs (test token: duffel_test_...)
    duffel_api_key: str = ""
    duffel_api_base: str = "https://api.duffel.com"
    # Card vault (PCI) — https://duffel.com/docs/api/v2/card/create-card
    duffel_cards_base: str = "https://api.duffel.cards"
    # Dev only: e.g. secure_corporate_payment for frictionless 3DS (see Duffel corporate cards guide).
    duffel_three_ds_exception: str = ""
    # LLM: auto = prefer DeepSeek key if set, else OpenAI
    llm_provider: str = "auto"
    deepseek_api_key: str = ""
    # ReAct / tools: use deepseek-chat. R1 cannot call tools — use deepseek_reasoning_model for a second pass only.
    deepseek_model: str = "deepseek-chat"
    deepseek_reasoning_model: str = "deepseek-reasoner"
    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_model: str = "gpt-4o-mini"
    # Optional: Discord bot (starts automatically with uvicorn when set)
    discord_bot_token: str = ""
    discord_command_prefix: str = "!flight"
    # Dev only: skip TLS verify for Discord aiohttp (insecure). Set DISCORD_INSECURE_SSL=1 if nothing else works.
    discord_insecure_ssl: bool = False
    # Optional: email itinerary after booking (book_flight_offer). Use Mailpit/Mailhog locally.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True
    smtp_ssl: bool = False


settings = Settings()
