# PDF.js 静态文件说明（KeApprove / 其他项目复用）

## KeApprove 校章页（`seal.html`）

- 依赖：`/js/pdf.min.js`、`/js/pdf.worker.min.js`
- **主文件与 worker 必须为同一版本**（推荐 **pdfjs-dist 2.16.105** 的 `build/pdf.min.js` 与 `build/pdf.worker.min.js`）。
- 下载（任选其一镜像）：
  - https://cdn.jsdelivr.net/npm/pdfjs-dist@2.16.105/build/pdf.min.js
  - https://cdn.jsdelivr.net/npm/pdfjs-dist@2.16.105/build/pdf.worker.min.js

## TeacherDataSystem 等其他项目

1. **若页面用 `<script>` + 全局 `pdfjsLib`**（与 `seal.html` 相同用法）：  
   将上述**两个文件复制到该项目自己的静态目录**（如 `static/js/`），并把 HTML 里的路径改成该项目能访问的 URL（例如 `/static/js/pdf.min.js`）。**不要**跨站点引用 KeApprove 的 `/js/`，除非两个应用部署在同一域名且路径一致。

2. **若前端用 npm `pdfjs-dist` + 打包**：无需复制这两个文件，在 `package.json` 中安装对应版本的 `pdfjs-dist` 即可。

## 校验

浏览器打开：`http://你的服务/js/pdf.min.js` 应返回 JS 内容而非 404；加载 PDF 后控制台不应出现 `pdfjsLib is not defined`。
