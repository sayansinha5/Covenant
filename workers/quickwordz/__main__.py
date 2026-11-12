from common.server import build_app, make_card, serve
from common.settings import Settings
from quickwordz.agent import write_copy

settings = Settings()
app = build_app(
    make_card(
        "QuickWordz",
        "Writes short product descriptions.",
        settings.quickwordz_public_url,
        [("copy", "Short product copy", ["copywriting"])],
    ),
    lambda message: write_copy(settings, message),
    settings.quickwordz_auth_token,
)


def main() -> None:
    serve(app, settings, settings.quickwordz_port)


if __name__ == "__main__":
    main()
