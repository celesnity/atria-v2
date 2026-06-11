"""Interactive setup wizard for first-time configuration."""

import json
import os
from typing import Optional

from rich.console import Console

from .interactive_menu import InteractiveMenu
from .wizard_ui import (
    rail_answer,
    rail_confirm,
    rail_error,
    rail_info_box,
    rail_intro,
    rail_outro,
    rail_prompt,
    rail_separator,
    rail_step,
    rail_success,
    rail_summary_box,
    rail_warning,
)
from atria.core.paths import get_paths, APP_DIR_NAME


console = Console()


def run_setup_wizard() -> bool:
    """Run the interactive setup wizard.

    Returns:
        True if setup completed successfully, False otherwise
    """
    rail_intro(
        "Welcome to Atria!",
        [
            "First-time setup detected.",
            "Let's configure your OpenAI-compatible endpoint.",
        ],
    )

    # Step 1: API base URL (optional)
    rail_step("API Base URL (optional)")
    api_base_url = rail_prompt(
        "Enter API base URL (leave blank for OpenAI default):",
        default="",
    )
    if not api_base_url:
        api_base_url = None

    # Step 2: API key
    rail_step("API Key")
    env_key = os.getenv("OPENAI_API_KEY")
    if env_key:
        if rail_confirm("Found $OPENAI_API_KEY in environment. Use it?", default=True):
            api_key = None  # will be picked up from env at runtime
            rail_success("Using API key from environment")
        else:
            api_key = rail_prompt("Enter your API key:", password=True)
            if not api_key:
                rail_error("No API key provided")
                return False
    else:
        api_key = rail_prompt("Enter your API key:", password=True)
        if not api_key:
            rail_error("No API key provided")
            return False

    # Step 3: Model
    model_id = select_model_direct()
    if not model_id:
        return False

    # Look up model info for smart defaults
    from atria.config import get_model_registry

    registry = get_model_registry()
    normal_model_result = registry.find_model_by_id(model_id)
    normal_model_info = normal_model_result[2] if normal_model_result else None

    # Step 4: Thinking model
    thinking_model = configure_slot_model(
        slot_name="Thinking",
        slot_description="Used for complex reasoning and planning tasks.",
        step_label="4 of 7",
        normal_model_info=normal_model_info,
        normal_model_id=model_id,
    )

    # Step 5: Critique model
    critique_model = configure_slot_model(
        slot_name="Critique",
        slot_description="Used for self-critique of reasoning. Falls back to Thinking model.",
        step_label="5 of 7",
        normal_model_info=normal_model_info,
        normal_model_id=thinking_model,
    )

    # Step 6: Vision model
    vlm_model = configure_slot_model(
        slot_name="Vision",
        slot_description="Used for image and screenshot analysis.",
        step_label="6 of 7",
        normal_model_info=normal_model_info,
        normal_model_id=model_id,
    )

    # Step 7: Summary + save
    config: dict = {
        "model": model_id,
        "auto_save_interval": 5,
        "model_thinking": thinking_model,
        "model_critique": critique_model,
        "model_vlm": vlm_model,
    }
    if api_key:
        config["api_key"] = api_key
    if api_base_url:
        config["api_base_url"] = api_base_url

    show_config_summary(config, {})

    if not rail_confirm("Save configuration?", default=True):
        rail_warning("Setup cancelled")
        return False

    if save_config(config):
        rail_success(f"Configuration saved to ~/{APP_DIR_NAME}/settings.json")
        rail_separator()
        rail_outro("All set! Starting Atria...")
        return True

    return False


def configure_slot_model(
    *,
    slot_name: str,
    slot_description: str,
    step_label: str,
    normal_model_info,
    normal_model_id: str,
) -> str:
    """Configure an optional model slot.

    Returns:
        model_id — either the normal model or a custom one.
    """
    model_name = normal_model_info.name if normal_model_info else "your model"

    rail_info_box(f"{slot_name} Model", [slot_description], step_label=step_label)

    menu_items = [
        ("use_normal", f"Use {model_name}", "Same model, no extra setup needed"),
        ("choose_manually", "Choose manually", "Enter a different model ID"),
    ]
    menu = InteractiveMenu(items=menu_items, title=f"Select {slot_name} Model", window_size=2)
    choice = menu.show()

    if choice != "choose_manually":
        return normal_model_id

    custom_id = rail_prompt("Enter model ID:")
    return custom_id if custom_id else normal_model_id


def show_config_summary(config: dict, _collected_keys: dict) -> None:
    """Display a summary panel of the configuration before saving."""
    from atria.config import get_model_registry

    registry = get_model_registry()

    def _model_display(model_id: str) -> str:
        result = registry.find_model_by_id(model_id)
        return result[2].name if result else model_id

    rows = [("Normal:", _model_display(config["model"]))]
    if config.get("model_thinking"):
        rows.append(("Thinking:", _model_display(config["model_thinking"])))
    if config.get("model_critique"):
        rows.append(("Critique:", _model_display(config["model_critique"])))
    if config.get("model_vlm"):
        rows.append(("Vision:", _model_display(config["model_vlm"])))
    if config.get("api_base_url"):
        rows.append(("Base URL:", config["api_base_url"]))

    extra_lines = []
    if os.getenv("OPENAI_API_KEY"):
        extra_lines = ["API Keys:", "  $OPENAI_API_KEY ✓"]

    rail_summary_box("Configuration Summary", rows, extra_lines=extra_lines)


def select_model_direct() -> Optional[str]:
    """Prompt for a model ID directly."""
    rail_step("Select Model")
    model_id = rail_prompt("Enter model ID (e.g. gpt-4o, claude-3-5-sonnet-20241022):")
    if not model_id:
        rail_warning("No model provided")
        return None
    rail_answer(model_id)
    return model_id


def save_config(config: dict) -> bool:
    """Save configuration to settings.json."""
    try:
        paths = get_paths()
        paths.global_dir.mkdir(parents=True, exist_ok=True)

        config_file = paths.global_settings
        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)

        return True
    except Exception as e:
        rail_error(f"Failed to save configuration: {e}")
        return False


def config_exists() -> bool:
    """Check if configuration file exists."""
    return get_paths().global_settings.exists()
