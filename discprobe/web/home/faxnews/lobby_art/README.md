# 大厅里的新闻传真机：怎么烘出来的

场景是 `art/desk/review-20261111/round5/room_round5.blend`（当前大厅那份），渲染器是同目录的 `render_round5.py`，只改了两处（见 `render_round5_to_render_fax.diff`）：`--device CPU` 时真的用 CPU（三台机器的显卡当时都被别的任务占着），底图“变化的投影”只算传真机、文件盒、包裹。描边、材质、灯光、雾都没动。

1. `place_fax.py`：在 round5 场景的副本里把文件盒挪 (+90, -250) mm（往左下、往桌子前沿，挪完仍在画面里），把 `art/desk/fax-news/fax_news.blend` 的 49 个零件按 0.9 倍放到左翼 (1250, -2400, 750) mm，正面朝左下；`--parcel` 再在显示器右边放一个 280 × 200 × 160 mm 的牛皮纸包裹盒。顺带写出投影点击区和标签要用的顶点。
2. `run_final.sh`：在 x79 上用 CPU 渲 base、faxnews、filebox，以及带包裹的 base、parcel（ss 4，纸色和墨色），约 1 小时。
3. `export_fax_lobby.py`：从提交过的 `lobby.json` 出发，只改 base、filebox、新加 faxnews 和 parcel（parcel 平时隐藏，自带接触阴影），信件托盘的点击区改成托盘和桌签两块轮廓的并集，给包裹让出位置；最后列出 1280 宽时不足 40 px 的点击区间距。

已知：传真机只放得下 0.9 倍，比光驱（2.9 倍）小很多；文件盒和传真机、光驱和传真机的点击区间距不到 40 px（数字见导出时的输出）。
