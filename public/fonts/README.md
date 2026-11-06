# 内部测试字体

来源为用户提供的项目根目录 `iPlaySoft.com-苹果苹方字体全套 (2)/`，原始 TTF 保持不变。三个 WOFF2 文件随本地页面提供，无需访问字体 CDN 或安装系统字体。

| 网页文件 | 字体内部名称 | CSS 权重 |
| --- | --- | --- |
| pingfang-sc-regular.woff2 | .PingFang-SC-Regular | 400 |
| pingfang-sc-medium.woff2 | .PingFang-SC-Medium | 500 |
| pingfang-sc-semibold.woff2 | .PingFang-SC-Semibold | 600 |

按字体内部名称识别字重，不以中文文件名推断。原包的 OS/2 权重均为 400；派生文件分别修正为上表权重，完整保留字符映射，不做字符子集裁剪。字体声明与全局字体栈见 `src/fonts.css`。

本目录用于用户已确认的内部测试场景。
