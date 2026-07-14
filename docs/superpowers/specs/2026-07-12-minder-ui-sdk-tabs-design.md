# minder_ui_sdk — Tabs của module (host header driven)

**Ngày:** 2026-07-12
**Branch gốc:** feat/rebrand-minder
**Trạng thái:** Design approved — chờ implementation plan

## 1. Mục tiêu

Một module có thể có nhiều tabs (nhiều trang). Hiện `module_template` (module
federation React) tự khai báo `const TABS` trong `DashboardApp.tsx` và tự vẽ
header + tab bar bên trong bundle của nó, trong khi host web-ui đã có sẵn cơ chế
render tabs ở top-bar (`ModuleTabs.tsx`) đọc từ `manifest.json → dashboard.tabs`.
Kết quả: hai nguồn khai báo tabs, và với module federation thì host **không**
truyền tab đang active xuống nên header top-bar không điều khiển được module.

Mục tiêu: module khai báo tabs **một lần** trong TS; khai báo đó vừa sinh
`dashboard.tabs` cho host top-bar, vừa quyết định panel nào render. Host điều
khiển tab **một chiều** (`activeTab` prop → module). Đổi tabs trong code →
rebuild → header tự cập nhật. Đổi module → header đổi bộ tabs tương ứng.

## 2. Quyết định thiết kế (đã chốt)

- **Single source of truth:** TS UI SDK (khai báo tabs bằng TS).
- **Đồng bộ lên host:** build/codegen ghi `manifest.json → dashboard.tabs`
  (host giữ nguyên cách đọc; header hiện tabs ngay khi list module, không cần
  load remote).
- **Chrome:** bỏ tab bar tự vẽ trong module; giữ header gradient + stat cards
  làm nội dung (slot cố định). Host top-bar sở hữu Back + title + tab row.
  Luồng một chiều host → module (`activeTab` prop).
- **Đóng gói:** package TS top-level riêng `minder_ui_sdk/` (sibling của
  `minder_module_sdk/`), npm name `minder-ui-sdk`, kèm vite plugin codegen.
- **`icon`:** giữ trong khai báo TS (module dùng nội bộ); codegen chỉ ghi
  `{id, label}` vào manifest (host `ModuleTabs` hiện chỉ render label).

## 3. Hiện trạng codebase (tham chiếu)

Host (web-ui) — đã có, giữ nguyên trừ 1 sửa nhỏ ở mục 4c:
- `web-ui/src/stores/modules.ts` — `summarize()` đọc `manifest.dashboard.tabs`
  (`Array<{id,label,entry?}>`) vào `ModuleSummary.tabs`; `activeModuleTab`,
  `setModuleTab`, `openDashboard` chọn `tabs[0]`, `closeDashboard`.
- `web-ui/src/components/Layout/ModuleTabs.tsx` — render `mod.tabs` thành tab
  row ở top-bar; render null nếu không có tab. Chỉ dùng `tab.label`.
- `web-ui/src/api/modules.ts` — type `ModuleTab { id; label; entry? }`,
  `ModuleDashboardManifest.tabs?`.
- `web-ui/src/components/ModuleDashboard/ModuleDashboardView.tsx` — nhánh
  `summary.remote` render `<RemoteDashboard summary={...}/>`; nhánh iframe dùng
  `moduleTabSrc()` (đã điều khiển được tab qua src). `activeTabId` đã có sẵn
  trong component.
- `web-ui/src/components/ModuleDashboard/RemoteDashboard.tsx` — load federated
  component, render `<Comp apiBase={...}/>` — **chỉ truyền apiBase** (đây là
  khoảng trống cho module federation).

Module (`modules/module_template/`):
- `frontend/vite.config.ts` — `@module-federation/vite`, expose
  `./Dashboard` = `./src/DashboardApp.tsx`, build `outDir: dist`.
- `frontend/src/DashboardApp.tsx` — `const TABS`, `useState(tab)`, tự vẽ header
  + stat cards + tab bar + panel switch.
- `frontend/src/panels/{Jobs,Media,Data,Metrics}Panel.tsx` — nhận `apiBase`.
- `manifest.json` — có `dashboard` + `remote`, **chưa có** `dashboard.tabs`.

Scaffolder:
- `minder/module_dev.py` — CLI `minder-module` (`new` gọi
  `store.create_module(template="service")`, `dev` chạy backend + `npm run dev`).
- Template `service` nằm trong `minder/core/modules/store` (nguồn scaffold cho
  frontend/manifest của module mới).

## 4. Thành phần

### 4a. Package `minder_ui_sdk/` (mới)

```
minder_ui_sdk/
  package.json          # name: "minder-ui-sdk", type: module, exports "." và "./vite"
  tsconfig.json
  src/
    defineDashboard.tsx
    vitePlugin.ts
    icons.ts
    index.ts            # export { defineDashboard, type DashboardConfig, type TabDef }
    vite.ts             # export { minderTabsSync }
  tests/
  README.md
```

`defineDashboard(config)`:
```ts
interface TabDef {
  id: string;
  label: string;
  icon?: string;                 // tên lucide, dùng nội bộ; KHÔNG ghi vào manifest
  component: React.ComponentType<{ apiBase: string }>;
}
interface DashboardConfig {
  title?: string;
  header?: React.ComponentType<{ apiBase: string }>;   // slot cố định (stat cards, health)
  tabs: TabDef[];
}
interface DashboardProps { apiBase: string; activeTab?: string | null; }

function defineDashboard(config: DashboardConfig): React.FC<DashboardProps> & {
  meta: { tabs: Array<{ id: string; label: string }>; title?: string };
};
```
- Component trả về: render `config.header` (nếu có) cố định phía trên, rồi
  render `config.tabs.find(t => t.id === activeTab)?.component` — fallback
  `tabs[0]` khi `activeTab` null/không khớp. **Không** render tab bar.
- `.meta.tabs` là data thuần (`{id,label}`), không chứa `component`, để vite
  plugin đọc mà không phải render React.

`minderTabsSync(options?)` — vite plugin:
- Options: `{ configModule?: string; manifestPath?: string }` — mặc định
  `configModule = "src/dashboard.tsx"` (module export default = kết quả
  `defineDashboard`), `manifestPath = "../manifest.json"` (tương đối frontend/).
- Hook `buildStart` (và `configureServer` cho dev): dùng
  `this.load` / vite SSR (`server.ssrLoadModule` hoặc esbuild transform) để nạp
  `configModule`, đọc `default.meta.tabs`.
- **Merge** vào manifest: đọc JSON hiện có, set
  `manifest.dashboard.tabs = meta.tabs` (giữ nguyên mọi field khác:
  `display_name`, `remote`, `dashboard.title`, ...), ghi lại với indent 2.
- Fail-soft: manifest thiếu / không parse / không ghi được → `this.warn(...)`,
  không throw (không làm fail build).
- Chỉ ghi khi nội dung `tabs` thực sự đổi (tránh churn/vòng lặp watch khi dev).

### 4b. Refactor `modules/module_template/frontend`

- `package.json`: thêm dep `"minder-ui-sdk": "file:../../../minder_ui_sdk"`.
- `vite.config.ts`: import và thêm `minderTabsSync()` vào `plugins`.
- Tạo `src/dashboard.tsx`:
  ```ts
  import { defineDashboard } from "minder-ui-sdk";
  import StatHeader from "./ui/StatHeader";   // stat cards + health tách ra
  import JobsPanel from "./panels/JobsPanel";
  // ...
  export default defineDashboard({
    title: "Module Template · SDK showcase",
    header: StatHeader,
    tabs: [
      { id: "jobs", label: "Jobs", icon: "briefcase", component: JobsPanel },
      { id: "media", label: "Media", icon: "image", component: MediaPanel },
      { id: "data", label: "Data", icon: "database", component: DataPanel },
      { id: "metrics", label: "Metrics", icon: "bar-chart", component: MetricsPanel },
    ],
  });
  ```
- `vite.config.ts` expose `./Dashboard` = `./src/dashboard.tsx` (thay
  `./src/DashboardApp.tsx`). Giữ `./ShowcaseBlock` như cũ.
- Tách phần header gradient + stat cards + health dot từ `DashboardApp.tsx`
  thành `src/ui/StatHeader.tsx` (nhận `apiBase`). Xóa `const TABS`,
  `useState(tab)`, tab bar, panel switch thủ công trong `DashboardApp.tsx`
  (file này có thể xóa hoặc rỗng hóa nếu không còn tham chiếu).
- `manifest.json`: sau build sẽ có `dashboard.tabs` (commit kết quả).

### 4c. Sửa host (web-ui) — truyền activeTab cho module federation

- `RemoteDashboard.tsx`: thêm prop `activeTab?: string | null`; render
  `<Comp apiBase={summary.api_base ?? ''} activeTab={activeTab ?? null} />`.
- `ModuleDashboardView.tsx` (nhánh `summary.remote`): truyền
  `activeTab={activeTabId}` vào `<RemoteDashboard .../>`. `activeTabId` đã có
  sẵn ở dòng `const activeTabId = useModulesStore(s => s.activeModuleTab)`.
- Không đổi `ModuleTabs`, store, hay type `ModuleTab` (đã đủ).

### 4d. Scaffolder

- Cập nhật template `service` trong `minder/core/modules/store` để module mới
  sinh ra đã có: `minder-ui-sdk` file-dep, `minderTabsSync()` trong vite config,
  `src/dashboard.tsx` mẫu `defineDashboard`, và expose `./Dashboard` trỏ vào
  `dashboard.tsx`. (Đường dẫn `file:` tương đối tính theo vị trí module trong
  `modules/<name>/frontend/` — cần khớp độ sâu; nếu template render động thì
  chèn đường dẫn đúng.)

## 5. Luồng dữ liệu

```
Build:   src/dashboard.tsx (defineDashboard) --minderTabsSync--> manifest.json dashboard.tabs (merge {id,label})
Runtime: manifest → store.summarize().tabs → ModuleTabs (top-bar row)
         click tab → setModuleTab(id) → activeModuleTab
         → ModuleDashboardView (remote) → RemoteDashboard(activeTab)
         → <Dashboard apiBase activeTab> → render header slot + panel khớp id
Đổi module: openDashboard(name) → activeModuleTab = tabs[0] → header đổi bộ tabs
Đổi tabs:   sửa dashboard.tsx → rebuild → plugin ghi manifest → header cập nhật
```

## 6. Edge cases

- `activeTab` null / không khớp id → fallback `tabs[0]`.
- Module không khai báo tabs (`tabs: []` hoặc không dùng SDK) → `ModuleTabs`
  render null; module single-view như hiện tại.
- Plugin: manifest thiếu / lỗi ghi → warn, build vẫn thành công.
- Plugin chỉ ghi khi `tabs` đổi → tránh watch-loop khi dev.
- Manifest merge, không ghi đè toàn file → không mất `remote`, `display_name`,...

## 7. Testing

Unit (TS, trong `minder_ui_sdk/tests/` — vitest):
- `defineDashboard`: render đúng panel theo `activeTab`; fallback `tabs[0]` khi
  null/không khớp; render `header` slot; không render tab bar.
- `.meta.tabs` = `[{id,label}]`, không chứa `component`.
- `minderTabsSync`: cho config → ghi đúng `dashboard.tabs`, giữ nguyên field
  khác của manifest; manifest thiếu → warn không throw; không ghi khi tabs
  không đổi.

Host (web-ui, vitest):
- `RemoteDashboard` truyền `activeTab` xuống `<Comp>`.
- `ModuleDashboardView` (remote) truyền `activeTabId` vào `RemoteDashboard`.
- `modules.tabs.test.ts` hiện có — vẫn xanh.

E2E (thủ công, theo CLAUDE.md — real run):
- `minder-module dev module_template` + `make run` web-ui.
- Mở module → header top-bar hiện 4 tabs; click tab → panel đổi (không reload
  cả bundle); đổi sang module khác → header đổi bộ tabs; đổi tabs trong
  `dashboard.tsx` → rebuild → header phản ánh.

## 8. Ngoài phạm vi (YAGNI)

- Hai chiều `onTabChange` (module tự đổi tab) — chỉ làm một chiều host → module.
- Runtime remote expose config — dùng codegen manifest thay thế.
- Đổi host `ModuleTabs` để render icon — giữ label-only.
- Hỗ trợ iframe module trong UI SDK — iframe đã hoạt động qua `moduleTabSrc`
  (manifest tabs + hash); UI SDK nhắm module federation React.
