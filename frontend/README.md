# Frontend 开发说明

当前 `frontend/` 是 TripPlannerDemo 的前端项目，使用 `Vue 3 + TypeScript + Vite + Ant Design Vue + Axios`。它已经不再只是骨架页，而是可以和后端完成生成、保存、历史、地图、天气、编辑和导出的完整联调。

## 1. 当前能力

- 规划页：填写目的地、日期、人数、预算、偏好和备注，调用 `/trip/generate`
- 结果页：展示行程概览、预算明细、按天花费、地图、天气、点位图片和每日安排
- 保存：调用 `/trip/save`
- 历史列表：调用 `/trip` 和 `/trip/{trip_id}`
- 删除历史行程：调用 `DELETE /trip/{trip_id}`
- 智能调整：调用 `/trip/edit`
- 导出：支持 PDF / Markdown，导出前会先保存当前页面数据
- 地图：接入高德 JavaScript API
- 天气：展示后端 `/weather/forecast` 返回的天气预报

## 2. 目录结构

```text
frontend/
├── src/
│   ├── components/
│   │   └── AmapTripMap.vue
│   ├── services/
│   │   └── api.ts
│   ├── types/
│   │   └── index.ts
│   ├── views/
│   │   ├── History.vue
│   │   ├── Home.vue
│   │   └── Result.vue
│   ├── App.vue
│   └── main.ts
├── .env.example
├── index.html
├── package.json
├── tsconfig.json
└── vite.config.ts
```

## 3. 环境变量

在服务器的 `frontend/` 目录下创建 `.env`：

```env
VITE_API_BASE_URL=http://你的服务器地址:8000
VITE_AMAP_JS_KEY=你的高德 JavaScript API key
```

注意：

- 如果浏览器是在你自己的电脑打开，`VITE_API_BASE_URL` 不要写服务器内部的 `127.0.0.1`
- 高德前端地图需要 JavaScript API key，不是后端 Web 服务 key
- 修改 `.env` 后需要重启 `npm run dev`

## 4. 启动方式

### 安装依赖

```bash
cd ~/autodl-tmp/TripPlannerDemo/frontend
npm install
```

### 启动开发服务

```bash
cd ~/autodl-tmp/TripPlannerDemo/frontend
npm run dev
```

当前 `vite.config.ts` 已配置：

```ts
server: {
  host: "0.0.0.0",
  port: 5173,
}
```

浏览器访问：

```text
http://你的服务器地址:5173
```

## 5. 后端联调前提

前端运行前，后端需要先启动：

```bash
cd ~/autodl-tmp/TripPlannerDemo/backend
uvicorn app.api.main:app --host 0.0.0.0 --port 8000
```

浏览器能访问下面地址时，再打开前端：

```text
http://你的服务器地址:8000/
http://你的服务器地址:8000/docs
```

## 6. 常见问题

### 页面能打开，但生成行程失败

优先检查：

- 后端 `8000` 是否启动
- `frontend/.env` 的 `VITE_API_BASE_URL` 是否正确
- 修改 `.env` 后是否重启了前端
- 浏览器控制台是否有 CORS 或网络请求错误

### 地图不显示

优先检查：

- `VITE_AMAP_JS_KEY` 是否填写
- 这个 key 是否是高德 JavaScript API key
- itinerary 里是否已经有 `latitude` / `longitude`

### 导出 PDF 打开空白页

正常情况下后端应该看到：

```text
POST /trip/save
GET /export/{trip_id}/pdf
```

如果只看到 `POST /trip/save`，说明前端没有跳转到导出地址，先确认前端代码已经更新并重启。

### `npm run dev` 提示找不到 `package.json`

说明当前目录错了。前端命令必须在 `frontend/` 目录执行：

```bash
cd ~/autodl-tmp/TripPlannerDemo/frontend
```

不要在 `backend/` 目录运行 `npm run dev`。

## 7. 当前推荐验证顺序

1. 启动后端
2. 启动前端
3. 生成一条行程
4. 查看地图点位
5. 查看天气信息
6. 保存行程
7. 打开历史列表
8. 智能调整某一天
9. 导出 PDF
10. 删除测试行程
