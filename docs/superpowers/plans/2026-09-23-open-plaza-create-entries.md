# Open Plaza Creation Entries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add working creation entries to the knowledge-base, SOP, and tool plazas while preserving the current Skill visibility and administrator-only publication boundary.

**Architecture:** The reusable detail view renders a parent-supplied create label. `OpenPlatformPage` owns a four-kind label/route map, performs a click-time administrator check, selects the overall agent through the existing scope event, and enters each resource's existing creation screen. No backend, database, or resource schema change is needed.

**Tech Stack:** React 18, TypeScript, React Router, Vitest, Testing Library, existing `notify` and enterprise agent-scope event.

**Spec:** `docs/superpowers/specs/2026-09-23-open-plaza-create-entries-design.md`

## Global Constraints

- All signed-in users see the four resource create buttons; the digital-employee plaza has none.
- Only administrators can enter an Open Plaza creation flow; keep all existing server-side `ensure_open_gallery_admin` checks unchanged.
- Reuse `/enterprise/knowledge/new`, `/enterprise/general-skills/new?scope=gallery`, `/enterprise/skills/distill?mode=create&agent_id=<overall-id>`, and `/enterprise/tools/new`.
- Preserve the current Skill route, and give all four buttons the same non-administrator permission feedback.
- Put executable frontend tests under `src/tests/frontend/`; add English mappings for new Chinese UI text.
- Do not disturb the nine pre-existing dirty paths in the main checkout. Merge linearly into local `main` only after required validation and review; do not push or delete the source branch.

## File Map

- `src/frontend-enterprise/src/components/openPlatform/PlatformKindDetailView.tsx`: presentational create button and label only.
- `src/tests/frontend/components/openPlatform/PlatformKindDetailView.test.tsx`: label and absent-button rendering regression.
- `src/frontend-enterprise/src/pages/OpenPlatformPage.tsx`: creation configuration, permission feedback, overall-scope selection, and navigation.
- `src/tests/frontend/pages/OpenPlatformPage.test.tsx`: route, role, scope, and missing-overall regressions with mocked reads.
- `src/frontend-enterprise/src/i18n/en.json`: translations for new labels and permission feedback.
- `docs/DEVELOPMENT_LOG.md` and `docs/SESSION_HANDOFF.md`: append implementation evidence and current state as required by `AGENTS.md`.

## Review Focus

1. A non-administrator who has an employee selected must see each button but clicking it must neither change that selection nor enter a private creation page; Task 2 tests this.
2. An administrator whose agent fetch has no overall agent must get an error and remain on the plaza without changing scope; Task 2 tests this.
3. An overall agent ID containing reserved URL characters must be encoded in the SOP editor URL; Task 2 tests this.
4. A plaza with zero resource cards must still show its creation action after loading; Task 1 tests empty items for each resource kind.
5. The digital-employee plaza must not gain a generic creation action; Task 1 and Task 2 test this.

---

### Task 1: Make the reusable button label resource-specific

**Files:**
- Modify: `src/frontend-enterprise/src/components/openPlatform/PlatformKindDetailView.tsx:51-72,140-149`
- Create: `src/tests/frontend/components/openPlatform/PlatformKindDetailView.test.tsx`

**Interfaces:**
- Consumes: existing optional `onCreate: () => void` callback.
- Produces: optional `createLabel?: string` prop; when `onCreate` is present, the button shows `createLabel` (default `创建开放 Skill` for existing callers).

- [ ] **Step 0: Prepare and verify the isolated baseline.** Run `npm --prefix src/frontend-enterprise ci` in the managed worktree, then `npm --prefix src/frontend-enterprise test -- --maxWorkers=4` before editing product code. If dependency installation or the unchanged baseline fails, record the exact failure and ask the user whether to investigate or continue with a documented baseline exception.
- [ ] **Step 1: Write the failing component test.** Import `afterEach`, `it`, `expect`, `vi`, `cleanup`, `render`, `screen`, `userEvent`, `I18nProvider`, and `PlatformKindDetailView`; call `afterEach(cleanup)`. Use an empty `items` array and a minimal `<svg />` icon. Render the view for `knowledge`, `general-skills`, `skills`, and `tools` with the expected `createLabel` and `onCreate={vi.fn()}`; assert exactly one button with that accessible name and that clicking it invokes the callback. Render `agents` without `onCreate`; assert no button whose name starts with `创建开放`.

```tsx
const cases = [
  ['knowledge', '创建开放知识库'],
  ['general-skills', '创建开放 Skill'],
  ['skills', '创建开放 SOP'],
  ['tools', '创建开放工具'],
] as const;
for (const [kind, createLabel] of cases) {
  it(`shows ${createLabel} for ${kind} with no cards`, async () => {
    const onCreate = vi.fn();
    render(<I18nProvider><PlatformKindDetailView
      kind={kind} title="广场" subtitle="" countLabel="内容" signals={[]}
      icon={() => <svg />} items={[]} loading={false} employeeStats={() => []}
      onBack={vi.fn()} onRefresh={vi.fn()} onCreate={onCreate}
      createLabel={createLabel} onOpenItem={vi.fn()}
    /></I18nProvider>);
    await userEvent.setup().click(screen.getByRole('button', { name: createLabel }));
    expect(onCreate).toHaveBeenCalledOnce();
  });
}

it('has no resource-creation button for digital employees', () => {
  render(<I18nProvider><PlatformKindDetailView
    kind="agents" title="数字员工广场" subtitle="" countLabel="员工" signals={[]}
    icon={() => <svg />} items={[]} loading={false} employeeStats={() => []}
    onBack={vi.fn()} onRefresh={vi.fn()} onOpenItem={vi.fn()}
  /></I18nProvider>);
  expect(screen.queryByRole('button', { name: /^创建开放/ })).toBeNull();
});
```

- [ ] **Step 2: Run the focused test and confirm red.** Run `npm --prefix src/frontend-enterprise test -- PlatformKindDetailView.test.tsx`. Expected: knowledge/SOP/tool accessible-name assertions fail because the current label is fixed to `创建开放 Skill`.
- [ ] **Step 3: Implement the minimal prop change.** Add `createLabel?: string` to `PlatformKindDetailViewProps`, destructure it with `= '创建开放 Skill'`, and render `{createLabel}` inside the existing button. Do not change its layout or onClick behavior.

```tsx
// In PlatformKindDetailViewProps, beside onCreate:
createLabel?: string;
// In the existing function parameter destructuring, beside onCreate:
createLabel = '创建开放 Skill',
// In the existing UIButton body, replacing only the fixed text:
{createLabel}
```

Keep the existing component body and button styling.

- [ ] **Step 4: Run the focused test and confirm green.** Run `npm --prefix src/frontend-enterprise test -- PlatformKindDetailView.test.tsx`; expected: all resource-kind and no-button cases pass. Run `npm --prefix src/frontend-enterprise run test:typecheck`.
- [ ] **Step 5: Commit this independently testable unit.** Stage only the component and its test; commit `feat(platform): label resource creation actions`.

### Task 2: Connect all four plaza actions to existing creation screens

**Files:**
- Modify: `src/frontend-enterprise/src/pages/OpenPlatformPage.tsx:45-120,522-550`
- Modify: `src/frontend-enterprise/src/i18n/en.json`
- Create: `src/tests/frontend/pages/OpenPlatformPage.test.tsx`

**Interfaces:**
- Consumes: `PlatformKindDetailView.createLabel`, `isAdmin`, `agents`, `ENTERPRISE_AGENT_STORAGE_KEY`, React Router `navigate`, and the existing `ultrarag-enterprise-agent-scope-change` event.
- Produces: `PLATFORM_CREATION: Partial<Record<PlatformKind, { label: string; path: string }>>` and a local `createOpenResource(kind: PlatformKind): void` handler in `OpenPlatformPage`.

- [ ] **Step 1: Write red page tests with a fetch stub.** Render `OpenPlatformPage` in `I18nProvider` + `MemoryRouter` at `/enterprise/platform/:kind`, with a catch-all route echoing `pathname + search`. Mock the five catalog GETs to return an overall agent and empty resource arrays. For administrator cases, click each create button and assert the destination, stored overall ID, and scope event. For the SOP case use overall ID `overall/1?` and assert encoded `agent_id=overall%2F1%3F`. For an ordinary user, verify all four labels remain visible, clicking produces `notify.error('仅管理员可以创建开放广场内容')`, and neither route nor previously stored employee scope changes. Cover missing overall for an administrator and no create button for `/enterprise/platform/agents`.

```tsx
const paths = [
  ['knowledge', '创建开放知识库', '/enterprise/knowledge/new'],
  ['general-skills', '创建开放 Skill', '/enterprise/general-skills/new?scope=gallery'],
  ['skills', '创建开放 SOP', '/enterprise/skills/distill?mode=create&agent_id=overall%2F1%3F'],
  ['tools', '创建开放工具', '/enterprise/tools/new'],
] as const;

for (const [kind, label, destination] of paths) {
  it(`opens ${kind} creation in overall scope for an admin`, async () => {
    const fetchMock = stubCatalogFetch([{ id: 'overall/1?', is_overall: true }]);
    const dispatch = vi.spyOn(window, 'dispatchEvent');
    renderPage(kind, true);
    await waitForCatalogLoad(fetchMock);
    await userEvent.setup().click(screen.getByRole('button', { name: label }));
    expect(screen.getByTestId('location').textContent).toBe(destination);
    expect(localStorage.getItem('ultrarag_enterprise_agent_scope')).toBe('overall/1?');
    expect(dispatch).toHaveBeenCalledWith(expect.objectContaining({
      type: 'ultrarag-enterprise-agent-scope-change', detail: { agentId: 'overall/1?' },
    }));
  });
}
```

Define the harness in that test file (import `cleanup`, `render`, `screen`, `waitFor`, `userEvent`, `MemoryRouter`, `Route`, `Routes`, `useLocation`, `notify`, `I18nProvider`, `OpenPlatformPage`, and Vitest helpers):

```tsx
function stubCatalogFetch(agentRows: Array<{ id: string; is_overall: boolean }>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const body = String(input).includes('/api/enterprise/agents?') ? agentRows : [];
    return {
      ok: true, status: 200, statusText: 'OK',
      text: async () => JSON.stringify(body),
    } as Response;
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

function LocationEcho() {
  const location = useLocation();
  return <div data-testid="location">{`${location.pathname}${location.search}`}</div>;
}

function renderPage(kind: string, isAdmin: boolean) {
  return render(<I18nProvider><MemoryRouter initialEntries={[`/enterprise/platform/${kind}`]}>
    <Routes>
      <Route path="/enterprise/platform/:kind" element={<OpenPlatformPage
        isAdmin={isAdmin}
        currentUser={{ id: 'user-1', username: 'tester', tenant_id: 'tenant_demo', role: isAdmin ? 'admin' : 'member' }}
      />} />
      <Route path="*" element={<LocationEcho />} />
    </Routes>
  </MemoryRouter></I18nProvider>);
}

async function waitForCatalogLoad(fetchMock: ReturnType<typeof vi.fn>) {
  await waitFor(() => expect(fetchMock.mock.calls.some(([input]) =>
    String(input).includes('/api/enterprise/tools?'))).toBe(true));
  await waitFor(() => expect(document.querySelector('[aria-busy="true"]')).toBeNull());
}

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
```

Add these exact denial and unavailable-overall assertions; the no-button case renders `agents` and asserts that `queryByRole('button', { name: /^创建开放/ })` is null:

```tsx
it.each(paths)('denies ordinary-user %s creation without changing scope', async (kind, label) => {
  const fetchMock = stubCatalogFetch([{ id: 'overall-1', is_overall: true }]);
  window.localStorage.setItem('ultrarag_enterprise_agent_scope', 'employee-1');
  const error = vi.spyOn(notify, 'error');
  renderPage(kind, false);
  await waitForCatalogLoad(fetchMock);
  await userEvent.setup().click(screen.getByRole('button', { name: label }));
  expect(error).toHaveBeenCalledWith('仅管理员可以创建开放广场内容');
  expect(window.localStorage.getItem('ultrarag_enterprise_agent_scope')).toBe('employee-1');
  expect(screen.queryByTestId('location')).toBeNull();
});

it('does not navigate when the overall agent is missing', async () => {
  const fetchMock = stubCatalogFetch([]);
  const error = vi.spyOn(notify, 'error');
  renderPage('knowledge', true);
  await waitForCatalogLoad(fetchMock);
  await userEvent.setup().click(screen.getByRole('button', { name: '创建开放知识库' }));
  expect(error).toHaveBeenCalledWith('暂时无法找到开放广场');
  expect(window.localStorage.getItem('ultrarag_enterprise_agent_scope')).toBeNull();
  expect(screen.queryByTestId('location')).toBeNull();
});

it('does not show creation on the digital-employee plaza', async () => {
  const fetchMock = stubCatalogFetch([{ id: 'overall-1', is_overall: true }]);
  renderPage('agents', true);
  await waitForCatalogLoad(fetchMock);
  expect(screen.queryByRole('button', { name: /^创建开放/ })).toBeNull();
});
```

- [ ] **Step 2: Run the focused test and confirm red.** Run `npm --prefix src/frontend-enterprise test -- OpenPlatformPage.test.tsx`. Expected: knowledge/SOP/tool buttons are absent, and ordinary-user Skill behavior does not yet give the new permission feedback.
- [ ] **Step 3: Implement the minimal page change.** Add the four-entry `PLATFORM_CREATION` map, implement `createOpenResource`, and pass `creation?.label` / `creation ? () => createOpenResource(selectedKind) : undefined` into `PlatformKindDetailView`. Guard `!isAdmin` before looking up or storing the overall agent. Preserve the current unavailable-gallery message when the overall agent is missing. Set the same local-storage key, dispatch the same scope-change event, then navigate to the mapped path; append the encoded overall `agent_id` only for SOP.

```tsx
const PLATFORM_CREATION: Partial<Record<PlatformKind, { label: string; path: string }>> = {
  knowledge: { label: '创建开放知识库', path: '/enterprise/knowledge/new' },
  'general-skills': { label: '创建开放 Skill', path: '/enterprise/general-skills/new?scope=gallery' },
  skills: { label: '创建开放 SOP', path: '/enterprise/skills/distill?mode=create' },
  tools: { label: '创建开放工具', path: '/enterprise/tools/new' },
};

function createOpenResource(kind: PlatformKind): void {
  const creation = PLATFORM_CREATION[kind];
  if (!creation) return;
  if (!isAdmin) {
    notify.error('仅管理员可以创建开放广场内容');
    return;
  }
  const overall = agents.find((item) => item.is_overall);
  if (!overall) {
    notify.error('暂时无法找到开放广场');
    return;
  }
  window.localStorage.setItem(ENTERPRISE_AGENT_STORAGE_KEY, overall.id);
  window.dispatchEvent(new CustomEvent('ultrarag-enterprise-agent-scope-change', {
    detail: { agentId: overall.id },
  }));
  navigate(kind === 'skills'
    ? `${creation.path}&agent_id=${encodeURIComponent(overall.id)}`
    : creation.path);
}
```

Keep the action binding type-safe without a cast. Add English mappings for `创建开放知识库`, `创建开放 SOP`, `创建开放工具`, and `仅管理员可以创建开放广场内容`.

- [ ] **Step 4: Run focused and language checks.** Run `npm --prefix src/frontend-enterprise test -- OpenPlatformPage.test.tsx PlatformKindDetailView.test.tsx`, `npm --prefix src/frontend-enterprise run test:typecheck`, and `npm --prefix src/frontend-enterprise run i18n:check`. All must pass. Review `git diff` for accidental API/permission changes.
- [ ] **Step 5: Commit the page unit.** Stage only the page, English map, and page test; commit `feat(platform): open knowledge sop and tool creation`.

### Task 3: Integrated verification, role-page acceptance, and safe local merge

**Files:**
- Modify: `docs/DEVELOPMENT_LOG.md`
- Modify: `docs/SESSION_HANDOFF.md`

**Interfaces:**
- Consumes: both feature commits and the already-committed spec/plan.
- Produces: verification record and, only if safe, a linear local `main` integration. No push and no source-branch deletion.

- [ ] **Step 1: Run the complete frontend gate.** Run `npm --prefix src/frontend-enterprise test -- --maxWorkers=4`, `npm --prefix src/frontend-enterprise run test:typecheck`, `npm --prefix src/frontend-enterprise run i18n:check`, `npm --prefix src/frontend-enterprise run config:check`, `npm --prefix src/frontend-enterprise run build`, `src/backend/.venv/Scripts/python.exe src/tests/check_test_layout.py` if the worktree backend venv exists (otherwise use an available Python 3 interpreter), and `git diff --check`. Record exact counts and any baseline warnings.
- [ ] **Step 2: Verify route and role behavior in a browser.** Use a safe authenticated browser session if available to check administrator and ordinary-user visits to `/enterprise/platform/knowledge`, `/enterprise/platform/general-skills`, `/enterprise/platform/skills`, and `/enterprise/platform/tools`; confirm visible labels, admin navigation and ordinary-user permission feedback. Avoid creating real published resources during UI acceptance. If the browser bridge or accounts are unavailable, record the gap rather than claiming live role acceptance.
- [ ] **Step 3: Review the branch.** Compare `main@6501350..HEAD` with `code-review` / `superpowers:requesting-code-review` as applicable, resolve actionable findings, rerun affected checks, and confirm no sensitive or unrelated files changed.
- [ ] **Step 4: Record evidence and commit documentation.** Append changed paths, commands/results, browser status, risks, and next actions to `docs/DEVELOPMENT_LOG.md`; refresh `docs/SESSION_HANDOFF.md`. Commit only these documentation updates with `docs(platform): record plaza entry validation`.
- [ ] **Step 5: Integrate only when safe.** Recheck local `main` HEAD, its nine pre-existing dirty paths, and branch divergence. Preserve any overlapping uncommitted documentation before a linear squash/rebase integration; if exact preservation, conflict resolution, or required gates cannot be proven, stop and report the blocker rather than overwriting work. After integration, rerun the focused frontend tests and `git status` on `main`. Do not push or delete the feature branch.
