import { LitElement, css, html } from "lit";
import { customElement, property } from "lit/decorators.js";

/** Minimal shape of the `hass` object HA passes into a custom panel. */
interface HomeAssistant {
  states: Record<string, unknown>;
  connection: unknown;
}

/** Panel root element, registered by `panel.py` via `panel_custom`. */
@customElement("home-upkeep-panel")
export class HomeUpkeepPanel extends LitElement {
  @property({ attribute: false }) accessor hass: HomeAssistant | undefined;

  @property({ type: Boolean }) accessor narrow = false;

  @property({ attribute: false }) accessor route: unknown;

  @property({ attribute: false }) accessor panel: unknown;

  static styles = css`
    :host {
      display: block;
      padding: 24px;
      font-family: "Segoe UI", Roboto, sans-serif;
    }
  `;

  render() {
    const entityCount = this.hass ? Object.keys(this.hass.states).length : 0;
    return html`<p>Hello, ${entityCount} entities.</p>`;
  }
}
