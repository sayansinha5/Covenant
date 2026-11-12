from common.server import build_app, make_card, serve
from common.settings import Settings
from tally.agent import fill

settings = Settings()
app = build_app(
    make_card(
        "Tally",
        "Fills dimensions, fabric and care from a seller's notes.",
        settings.tally_public_url,
        [("catalogue", "Fill catalogue fields", ["catalog_data"])],
    ),
    lambda message: fill(settings, message),
    settings.tally_auth_token,
)


def main() -> None:
    serve(app, settings, settings.tally_port)


if __name__ == "__main__":
    main()
