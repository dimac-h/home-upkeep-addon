import { mdiPencil, mdiTrashCanOutline } from "@mdi/js";
import { LitElement, css, html } from "lit";
import { customElement, property } from "lit/decorators.js";

import type { TaskList } from "../ha-api";
import { icon } from "../icon";
import {
  buttonStyles,
  cardStyles,
  dialogStyles,
  iconButtonStyles,
  listItemStyles,
} from "../styles";

@customElement("home-upkeep-task-lists")
export class HomeUpkeepTaskLists extends LitElement {
  @property({ attribute: false }) lists: TaskList[] = [];

  @property({ type: Number }) selectedListId: number | undefined;

  @property({ type: Boolean }) mobileMenuOpen = false;

  static styles = [
    cardStyles,
    buttonStyles,
    iconButtonStyles,
    listItemStyles,
    dialogStyles,
    css`
      aside {
        display: none;
      }
      aside.mobile-open {
        display: block;
        position: fixed;
        inset-block: 0;
        left: 0;
        z-index: 50;
        width: 20rem;
      }
      @media (min-width: 1024px) {
        aside {
          display: block;
        }
        aside.mobile-open {
          position: static;
          width: auto;
        }
      }
      .mobile-overlay {
        display: none;
      }
      .mobile-overlay.open {
        display: block;
        position: fixed;
        inset: 0;
        z-index: 40;
        background: rgb(0 0 0 / 0.5);
      }
      @media (min-width: 1024px) {
        .mobile-overlay.open {
          display: none;
        }
      }
      .card-inner {
        height: 100%;
        overflow-y: auto;
        padding: 1.5rem;
        box-sizing: border-box;
      }
      .header {
        margin-bottom: 1.5rem;
        display: flex;
        align-items: center;
        justify-content: space-between;
      }
      ul {
        list-style: none;
        margin: 0;
        padding: 0;
        display: flex;
        flex-direction: column;
        gap: 0.5rem;
      }
      .row {
        display: flex;
        align-items: center;
        justify-content: space-between;
      }
      .name-button {
        flex: 1;
        text-align: left;
        font-weight: 500;
        color: var(--hu-gray-900);
        background: none;
        border: none;
        cursor: pointer;
        padding: 0;
        font-size: inherit;
        font-family: inherit;
      }
      .name-button:hover {
        color: var(--hu-blue-600);
      }
      .row-actions {
        margin-left: 0.5rem;
        display: flex;
        gap: 0.25rem;
      }
      .empty {
        padding: 1rem 0;
        text-align: center;
        font-size: 0.875rem;
        color: var(--hu-gray-500);
      }
      @media (prefers-color-scheme: dark) {
        .name-button {
          color: var(--hu-gray-100);
        }
        .name-button:hover {
          color: var(--hu-blue-400);
        }
        .empty {
          color: var(--hu-gray-400);
        }
      }
    `,
  ];

  private _fire(name: string, detail?: unknown) {
    this.dispatchEvent(
      new CustomEvent(name, { detail, bubbles: true, composed: true }),
    );
  }

  private _selectList(id: number) {
    this._fire("list-select", { id });
    if (this.mobileMenuOpen) {
      this._fire("mobile-menu-toggle");
    }
  }

  private _createList() {
    this._fire("list-create");
    if (this.mobileMenuOpen) {
      this._fire("mobile-menu-toggle");
    }
  }

  render() {
    return html`
      ${this.mobileMenuOpen
        ? html`<div
            class="mobile-overlay open"
            @click=${() => this._fire("mobile-menu-toggle")}
          ></div>`
        : null}
      <aside class=${this.mobileMenuOpen ? "mobile-open" : ""}>
        <div class="card card-inner">
          <div class="header">
            <h2 class="dialog-title">Lists</h2>
            <button class="btn-primary" @click=${() => this._createList()}>
              New List
            </button>
          </div>
          <nav>
            <ul>
              ${this.lists.map(
                (l) => html`
                  <li>
                    <div
                      class="list-item ${this.selectedListId === l.id
                        ? "list-item-selected"
                        : ""}"
                    >
                      <div class="row">
                        <button
                          class="name-button"
                          @click=${() => this._selectList(l.id)}
                        >
                          ${l.name}
                        </button>
                        <div class="row-actions">
                          <button
                            class="icon-button"
                            aria-label="Rename list ${l.name}"
                            title="Rename list"
                            @click=${() => this._fire("list-edit", { list: l })}
                          >
                            ${icon(mdiPencil)}
                          </button>
                          <button
                            class="icon-button-danger"
                            aria-label="Delete list ${l.name}"
                            title="Delete list"
                            @click=${() =>
                              this._fire("list-delete", { id: l.id })}
                          >
                            ${icon(mdiTrashCanOutline)}
                          </button>
                        </div>
                      </div>
                    </div>
                  </li>
                `,
              )}
              ${this.lists.length === 0
                ? html`<li class="empty">No lists yet</li>`
                : null}
            </ul>
          </nav>
        </div>
      </aside>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "home-upkeep-task-lists": HomeUpkeepTaskLists;
  }
}
