# 静态项目介绍页

这是 Texa 的独立宣传页面，不依赖 Node.js、打包器或外部 CDN。

在线演示：<https://jayceto946-byte.github.io/texa/>

## 直接打开

双击 index.html 即可。页面中的 CSS、JavaScript 和六张真实项目截图均使用相对路径。截图在独立资源区显示为固定比例缩略图，点击后通过原生 dialog 展开。

## 本地预览

在仓库根目录运行：

    .\venv310\Scripts\python.exe -m http.server 4173 --directory site

然后访问 <http://127.0.0.1:4173>。

## 目录

    site/
    ├── index.html
    ├── README.md
    └── assets/
        ├── styles.css
        ├── script.js
        └── images/

## 内容边界

- 截图来自隔离 demo 数据，不含 API Key、账号或正式学习数据。
- LLM、OCR、MinerU 和知识增强能力按依赖条件标注。
- 未完成能力统一列在 Roadmap。
- 仓库当前没有 LICENSE，页面没有声称采用任何开源协议。
- GitHub 入口指向仓库现有 remote：jayceto946-byte/texa。

## 发布

该目录通过 <code>.github/workflows/pages.yml</code> 自动部署到 GitHub Pages，也可以上传到任意静态文件服务器或对象存储。发布前仍应确认内置截图和样例教材相关内容的公开分发授权。
