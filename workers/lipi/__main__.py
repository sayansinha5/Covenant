from common.server import build_app, make_card, serve
from common.settings import Settings
from lipi.agent import translate

settings = Settings()
app = build_app(
    make_card(
        "Lipi",
        "Translates product listings and keeps names and prices as they are.",
        settings.lipi_public_url,
        [("translate", "Translate listings", ["translation"])],
    ),
    lambda message: translate(settings, message),
    settings.lipi_auth_token,
)


def main() -> None:
    serve(app, settings, settings.lipi_port)


if __name__ == "__main__":
    main()
