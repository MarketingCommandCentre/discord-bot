# Marketing Command Centre Bot

Discord bot for the Marketing Command Centre. Talks to the Marketing Command
Centre Spring Boot API over HTTP to manage marketing requests and audit events.

## Tech Stack
- Python (discord.py)
- aiohttp for API calls
- python-dotenv for configuration

## Running

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # then fill in your values
python main.py
```

## License

Copyright (C) 2026 Ibrahim Chehab

This program is free software: you can redistribute it and/or modify it under
the terms of the **GNU General Public License v3.0** as published by the Free
Software Foundation, either version 3 of the License, or (at your option) any
later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE. See the [GNU General Public License](./LICENSE) for more
details, or visit <https://www.gnu.org/licenses/gpl-3.0.html>.
