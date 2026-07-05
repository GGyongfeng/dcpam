/**
 * ConfigModule 组件：完整的 config.toml 渲染 + 编辑模块。
 * 包含标题行（折叠箭头 + "CONFIG" 标题 + 4 个操作按钮）+ 展开时的表单。
 *
 * 用法：
 *   <ConfigModule />
 *
 * 依赖：需要外层用 <ConfigProvider> 包住（见 layout/useConfig.jsx）。
 * 内容占满父容器宽度；不带外部间距和背景，让父级 section 决定。
 */
export { ConfigModule } from "./ConfigModule.jsx";
