# Open Plaza creation entries for knowledge, SOP, and tools

Date: 2026-09-23. Base: `main@6501350`. Target: local `main` after validation and review.

## Outcome and scope

The knowledge-base, SOP, and tool detail views in Open Plaza gain a create button like the existing Skill detail view. All signed-in users see the buttons. Creating content in the overall/Open Plaza scope remains administrator-only; this work does not grant new publication rights or change backend authorization, persistence, or resource schemas. The existing Skill button keeps its route but uses the same explicit permission feedback as the new buttons.

## Approach and navigation

Reuse the existing creation screens instead of introducing three separate plaza forms. `PlatformKindDetailView` accepts the button label from its parent. `OpenPlatformPage` supplies an action for each of the four resource kinds and leaves the digital-employee kind unchanged. For an authorized administrator, the action first selects the existing overall agent through the shared scope storage/event mechanism, then navigates to the appropriate form:

| Plaza kind | Button | Existing destination |
| --- | --- | --- |
| Knowledge base | 创建开放知识库 | `/enterprise/knowledge/new` |
| Skill | 创建开放 Skill | `/enterprise/general-skills/new?scope=gallery` |
| SOP | 创建开放 SOP | `/enterprise/skills/distill?mode=create&agent_id=<overall-id>` |
| Tool | 创建开放工具 | `/enterprise/tools/new` |

The SOP editor already creates a workspace ID when one is absent. Knowledge creation uses its existing document-upload flow; tool creation starts in its existing blank-tool form. Their existing create endpoints determine the resource type and accept the selected overall scope. No direct publish API call is added to the plaza page.

## Permissions and errors

The button is not hidden from non-administrators, matching the current Skill visibility. A non-administrator click reports that only administrators can create Open Plaza content and does not switch scope or enter a form that might silently create a private employee resource. If the overall agent is unavailable, the existing unavailable-gallery error appears and no navigation occurs. Server-side `ensure_open_gallery_admin` checks remain authoritative for all four resource kinds.

## Verification and limits

Focused frontend regression tests check button labels and presence for the four resource kinds, no button for digital employees, administrator destinations and overall-scope selection, and non-administrator/missing-overall behavior. Run the frontend suite, test typecheck, i18n check for new UI text, configuration check if relevant, and production build. Check the affected plaza routes in a browser for both administrator and ordinary-user roles when an authenticated session is available; report any unavailable live-role acceptance explicitly. A created item appearing in the plaza still depends on the existing resource-specific save/upload flow and a refresh; this change does not add a new publishing workflow.
