"""Design tokens do BookRoomLog: única fonte de cores, escalas e tipografia (QSS e QPalette)."""

COLORS = {
    # superfícies (do mais escuro ao mais claro)
    "bg": "#0b0c10",
    "surface": "#13151c",
    "surface_2": "#1a1d27",
    "surface_3": "#232735",
    "border": "#262a38",
    "border_strong": "#363c52",
    # texto
    "text": "#eef0f6",
    "text_muted": "#9aa1b5",
    "text_dim": "#6b7186",
    # acento
    "accent": "#f59e0b",
    "accent_hover": "#d97706",
    "accent_pressed": "#b45309",
    "accent_text": "#fcd34d",
    "accent_soft": "rgba(245, 158, 11, 0.16)",
    "accent_border": "rgba(245, 158, 11, 0.45)",
    # estados
    "success": "#34d399",
    "success_hover": "#2bb785",
    "danger": "#f87171",
    "danger_soft": "rgba(248, 113, 113, 0.14)",
    "danger_border": "rgba(248, 113, 113, 0.45)",
    "warning": "#fb923c",
    "on_accent": "#1c1203",
    "on_success": "#052e1f",
    "overlay": "rgba(255, 255, 255, 0.14)",
}

RADIUS = {"sm": 6, "md": 10, "lg": 14}
SPACING = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24}
FONT_SIZE = {"xs": 11, "sm": 12, "md": 13, "lg": 15, "xl": 20, "xxl": 26}
FONT_FAMILY = "Inter"
FONT_FALLBACK = '"Inter", "Segoe UI", "Noto Sans", sans-serif'


def qss_mapping() -> dict:
    """Dicionário usado para preencher os placeholders `$nome` do template QSS."""
    mapping = dict(COLORS)
    mapping.update({f"r_{k}": f"{v}px" for k, v in RADIUS.items()})
    mapping.update({f"s_{k}": f"{v}px" for k, v in SPACING.items()})
    mapping.update({f"fs_{k}": f"{v}px" for k, v in FONT_SIZE.items()})
    mapping["font_family"] = FONT_FALLBACK
    return mapping
