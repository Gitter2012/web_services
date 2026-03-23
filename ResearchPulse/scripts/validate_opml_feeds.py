#!/usr/bin/env python3
# =============================================================================
# 脚本: scripts/validate_opml_feeds.py
# 功能: 验证 OPML 导入的 RSS feeds 是否仍然有效，并生成可用于导入的 SQL
# 用法: python scripts/validate_opml_feeds.py
#       python scripts/validate_opml_feeds.py --dry-run   # 不写入 init.sql
#       python scripts/validate_opml_feeds.py --no-db     # 不连接数据库（仅用 init.sql 去重）
# 输出:
#   - 控制台: 有效/无效/已存在 汇总统计
#   - valid_new_feeds.sql: 可直接执行的 INSERT IGNORE 语句
#   - sql/init.sql (末尾追加): 同上（除非使用 --dry-run）
# =============================================================================

from __future__ import annotations

import argparse
import asyncio
import logging
import re
import sys
from datetime import date
from pathlib import Path
from typing import NamedTuple

# ── 确保项目根目录在 sys.path 中 ──────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# =============================================================================
# OPML 数据 (hardcoded — extracted from user-provided OPML file)
# 格式: (folder, title, xmlUrl, htmlUrl)
# =============================================================================
OPML_FEEDS: list[tuple[str, str, str, str]] = [
    # ── folder: "" (top-level / unlabeled) ───────────────────────────────────
    ("", "The npm Blog", "http://blog.npmjs.org/rss", ""),
    ("", "snoopyxdy的博客", "http://snoopyxdy.blog.163.com/rss/", ""),
    ("", "RisingStack Community", "https://community.risingstack.com/rss/", ""),
    ("", "Node.js Daily", "https://news.risingstack.com/rss", ""),
    ("", "Hack Sparrow", "http://feeds.feedburner.com/hacksparrow", ""),
    ("", "Nodejitsu", "http://blog.nodejitsu.com/feed.xml", ""),
    ("", "NodeUp", "http://feeds.feedburner.com/NodeUp", ""),
    ("", "Joyeur Article Feed", "http://joyent.com/blog/feed", ""),
    ("", "Node.js Blog", "https://nodejs.org/en/feed/blog.xml", ""),
    ("", "Vue.js - MVVM Made Simple", "https://www.reddit.com/r/vuejs/.rss", ""),
    ("", "Vue.js Feed", "https://vuejsfeed.com/feed", ""),
    ("", "破船之家", "http://beyondvincent.com/atom.xml", "http://beyondvincent.com/"),
    ("", "技术小黑屋", "http://droidyue.com/atom.xml", "http://droidyue.com/"),
    ("", "张明云的博客", "http://zmywly8866.github.io/pages/atom.xml", "http://zmywly8866.github.io"),
    ("", "开源实验室", "http://www.kymjs.com/feed.xml", "http://www.kymjs.com/"),
    ("", "子勰的博客", "http://blog.bihe0832.com/pages/atom.xml", "http://blog.bihe0832.com"),
    ("", "博客园_漫天尘沙", "http://feed.cnblogs.com/blog/u/162102/rss", ""),
    ("", "WaylenWang", "http://waylenw.github.io/atom.xml", "http://waylenw.github.io/"),
    ("", "云风的 BLOG", "http://blog.codingnow.com/atom.xml", "http://blog.codingnow.com/"),
    ("", "Yet Another Summer Rain", "http://www.liaohuqiu.net/atom.xml", "http://liaohuqiu.net/"),
    ("", "Trinea", "http://www.trinea.cn/feed/", "http://www.trinea.cn"),
    ("", "The Corner", "http://feeds.feedburner.com/corner-squareup-com", "http://corner.squareup.com"),
    ("", "Styling Android", "http://feeds.feedburner.com/StylingAndroid", ""),
    ("", "The Android Arsenal", "http://android-arsenal.com/rss.xml", ""),
    ("", "Mobile Internet developer", "http://blog.csdn.net/xiaanming/rss/list", ""),
    ("", "RaizException", "http://www.raizlabs.com/dev/feed/", "http://www.raizlabs.com/dev"),
    ("", "inovex-Blog", "https://blog.inovex.de/feed/", "https://blog.inovex.de"),
    ("", "Loader's Blog", "http://blog.csdn.net/qibin0506/rss/list", ""),
    ("", "Hellsoft", "http://www.hellsoft.se/feed/", ""),
    ("", "ImportNew", "http://www.importnew.com/feed", "http://www.importnew.com"),
    ("", "DBA Notes", "http://dbanotes.net/feed", "http://dbanotes.net"),
    ("", "coder-pig的猪栏", "http://blog.csdn.net/coder_pig/rss/list", ""),
    ("", "Beyond0525的专栏", "http://blog.csdn.net/beyond0525/rss/list", ""),
    ("", "ASCE1885", "http://blog.csdn.net/asce1885/rss/list", ""),
    ("", "Android Weekly Archive Feed", "http://us2.campaign-archive1.com/feed?u=887caf4f48db76fd91e20a06d&id=4eb677ad19", ""),
    ("", "Android开发技术周报", "http://www.androidweekly.cn/rss/", ""),
    ("", "Android Developers Blog", "http://feeds.feedburner.com/blogspot/hsDu", ""),
    ("", "Android Central", "http://www.androidcentral.com/feed", ""),
    ("", "风雪之隅", "http://www.laruence.com/feed", "http://www.laruence.com"),
    ("", "胡凯", "http://hukai.me/atom.xml", "http://hukai.me/"),
    ("", "酷壳 CoolShell", "http://coolshell.cn/feed", "http://coolshell.cn"),
    ("", "程序师", "http://www.techug.com/feed", "http://www.techug.com"),
    ("", "杨辉的个人博客", "http://yanghui.name/atom.xml", "http://yanghui.name/"),
    ("", "快乐de胖虎", "http://blog.csdn.net/u011133213/rss/list", ""),
    ("", "开发技术前线", "http://www.devtf.cn/?feed=rss2", ""),
    ("", "张兴业的博客", "http://blog.csdn.net/xyz_lmn/rss/list", ""),
    ("", "四火的唠叨", "http://www.raychase.net/feed", "http://www.raychase.net"),
    ("", "代码家", "http://blog.daimajia.com/rss/", "http://daimajia.com/"),
    ("", "Veaer|王扒蒜", "http://veaer.com/atom.xml", ""),
    ("", "wklken's blog", "http://www.wklken.me/feed.xml", ""),
    ("", "Tricky Android", "http://trickyandroid.com/rss/", ""),
    ("", "The Cheese Factory's Blog", "http://inthecheesefactory.com/blog/en/rss.xml", ""),
    ("", "Snow Memory", "http://andrewliu.in/atom.xml", "http://andrewliu.in/"),
    ("", "MacTalk-池建强的随想录", "http://macshuo.com/?feed=rss2", "http://macshuo.com"),
    ("", "Android Performance", "http://androidperformance.com/atom.xml", ""),
    ("", "Liter's Blog", "http://www.vmatianyu.cn/feed", ""),
    ("", "Hongyang", "http://blog.csdn.net/lmj623565791/rss/list", ""),
    ("", "Innost的专栏", "http://blog.csdn.net/innost/rss/list", ""),
    ("", "Drakeet的个人博客", "https://drakeet.me/feed", "https://drakeet.me"),
    ("", "FOOKWOOD", "http://www.fookwood.com/feed", ""),
    ("", "Dan Lew Codes", "http://blog.danlew.net/rss/", ""),
    ("", "Chris Banes", "https://chris.banes.me/atom.xml", ""),
    ("", "Antonio Leiva", "http://antonioleiva.com/feed/", ""),
    ("", "Android Niceties", "http://androidniceties.tumblr.com/rss", ""),
    ("", "Android – 伯乐在线", "http://blog.jobbole.com/category/android/feed/", ""),
    ("", "Android Design Patterns", "http://www.androiddesignpatterns.com/feed.atom", ""),
    ("", "AigeStudio", "http://blog.csdn.net/aigestudio/rss/list", ""),
    ("", "Framer Blog", "http://framerjs.tumblr.com/rss", ""),
    ("", "[ i D 公 社 ]", "http://feeds.feedburner.com/ID", "http://www.hi-id.com"),
    ("", "毓杰Oliver的Blog", "http://blog.oliverzy.gitpress.org/index/rss", ""),
    ("", "Groupon Engineering Blog", "https://engineering.groupon.com/feed/", ""),
    ("", "Teahour.fm", "http://teahour.fm/feed.xml", ""),
    ("", "Be For Web", "http://beforweb.com/rss.xml", ""),
    ("", "EmberJS.CN Blog", "http://emberjs.cn/blog/feed.xml", ""),
    ("", "InfoQ", "http://www.infoq.com/rss/rss.action?token=ou13lwDiwGTBAIVNjazCsFp6NtSRMUTj", ""),
    ("", "NullPointer的新无效地址", "http://npchen.blogspot.com/feeds/posts/default", ""),
    ("", "peter.michaux.ca", "http://peter.michaux.ca/feed/atom.xml", ""),
    ("", "Swaroop C H", "http://www.swaroopch.com/feed/", ""),
    ("", "Vimer", "http://feed.feedsky.com/vimer", ""),
    ("", "InfoQ CN", "http://www.infoq.com/cn/rss/rss.action?token=ou13lwDiwGTBAIVNjazCsFp6NtSRMUTj", ""),
    ("", "外刊IT评论", "http://feed.feedsky.com/aqee-net", ""),
    ("", "雨夜带刀's Blog", "http://stylechen.com/feed", ""),
    ("", "黑客志", "http://feed.feedsky.com/heikezhi", ""),
    ("", "Matrix67: My Blog", "http://www.matrix67.com/blog/feed.asp", ""),
    ("", "Fonts In Use", "http://feeds.feedburner.com/FontsInUse", ""),
    ("", "hax的技术部落格", "http://hax.iteye.com/rss", ""),
    ("", "James Burke", "http://jrburke.com/atom.xml", ""),
    ("", "JavaScript.com", "https://www.javascript.com/feed/rss", ""),
    ("", "MooTools", "http://feeds.feedburner.com/mootools-blog", ""),
    ("", "Smashing Magazine", "http://rss1.smashingmagazine.com/feed/", ""),
    ("", "岁月如歌", "http://lifesinger.wordpress.com/feed/", ""),
    ("", "韩寒", "http://blog.sina.com.cn/rss/twocold.xml", ""),
    ("", "粉丝日志", "http://blog.fens.me/feed/", ""),
    ("", "Coding Horror", "http://feeds.feedburner.com/codinghorror", ""),
    ("", "Julia Evans", "http://jvns.ca/atom.xml", "http://jvns.ca"),
    ("", "The GitHub Blog", "https://github.com/blog.atom", "https://github.com/blog"),
    ("", "Brendan Gregg's Blog", "http://www.brendangregg.com/blog/rss.xml", ""),
    ("", "高可用架构", "http://www.infoq.com/cn/architecture/rss/", ""),
    ("", "程序媛", "http://www.womenintechnology.co.uk/blog/rss", ""),
    ("", "thoughtbot", "https://robots.thoughtbot.com/rss.xml", ""),
    ("", "Inside Intercom", "https://blog.intercom.com/feed", ""),
    ("", "Airbnb Engineering", "http://nerds.airbnb.com/feed", ""),
    ("", "Artsy Engineering Blog", "http://artsy.github.io/atom.xml", ""),
    ("", "Stormpath", "http://feeds.feedburner.com/StormPath", ""),
    ("", "Backchannel", "https://medium.com/feed/backchannel", ""),
    ("", "Lenny Rachitsky", "https://www.lennyrachitsky.com/feed", ""),
    ("", "Palantir Blog", "https://medium.com/feed/palantir", ""),
    ("", "Instagram Engineering", "http://instagram-engineering.tumblr.com/rss", ""),
    ("", "Spotify Labs", "http://labs.spotify.com/feed/", ""),
    ("", "Grab Tech", "https://engineering.grab.com/feed.xml", ""),
    ("", "LessWrong", "http://lesswrong.com/.rss", ""),
    ("", "Zach Holman", "http://zachholman.com/feed.xml", ""),
    ("", "Steve Losh", "http://stevelosh.com/atom.xml", ""),
    ("", "张克军的博客", "http://hikejun.com/blog/?feed=rss2", ""),
    ("", "陈皓的技术博客", "http://www.hakanai.link/?feed=rss2", ""),
    ("", "Lifehacker", "http://feeds.gawker.com/lifehacker/vip", ""),
    ("", "六六六六六六", "http://liuliu.me/atom.xml", ""),
    ("", "Tim Pope's Blog", "http://tbaggery.com/atom.xml", ""),
    ("", "Tavis Rudd", "http://tavisrudd.github.io/atom.xml", ""),
    ("", "Piotr Solnica", "http://solnic.eu/atom.xml", ""),
    ("", "Robert Heaton", "https://robertheaton.com/feed.xml", ""),
    ("", "Justin Duke", "http://jmduke.com/atom.xml", ""),
    ("", "张天雷", "http://www.zenlife.tk/feed.atom", ""),
    ("", "I, Programmer", "http://www.i-programmer.info/index.php?format=feed&type=rss", ""),
    ("", "The Register", "http://www.theregister.co.uk/headlines.atom", ""),
    ("", "Mattermark", "http://mattermark.com/feed/", ""),
    ("", "Lian Qingzhan的博客", "http://lianqingzhan.github.io/atom.xml", ""),
    ("", "BangBangCon", "http://bangbangcon.com/feed.xml", ""),
    ("", "OverAPI.com", "http://overapi.com/rss.xml", ""),
    ("", "Antirez weblog", "http://antirez.com/rss", ""),
    ("", "Linux Inside", "https://0xax.gitbooks.io/linux-insides/content/rss.xml", ""),
    ("", "Grokbase", "http://grokbase.com/search?query=node.js&format=rss", ""),
    ("", "Jim Weirich", "http://onestepback.org/index.cgi/atom", ""),
    ("", "Mike Ash", "https://www.mikeash.com/pyblog/rss.py", ""),
    ("", "NSHipster", "http://nshipster.com/feed.xml", ""),
    ("", "Natasha The Robot", "https://www.natashatherobot.com/feed/", ""),
    ("", "objc.io", "http://www.objc.io/feed.xml", ""),
    ("", "Cocoa with Love", "http://cocoawithlove.com/feed.xml", ""),
    ("", "iOS Dev Weekly", "https://iosdevweekly.com/issues.rss", ""),
    ("", "AppCoda", "http://www.appcoda.com/feed/", ""),
    ("", "Raywenderlich", "http://www.raywenderlich.com/feed/", ""),
    ("", "swift.gg", "http://swift.gg/feed.xml", ""),
    ("", "SwiftRocks", "https://swiftrocks.com/rss.xml", ""),
    ("", "Ole Begemann", "https://oleb.net/blog/atom.xml", ""),
    ("", "点滴一粟", "http://www.niudaren.me/rss.xml", ""),
    ("", "MrPeak杂货铺", "http://mrpeak.cn/atom.xml", ""),
    ("", "OneV's Den", "https://onevcat.com/feed.xml", ""),
    ("", "南峰子_老驴", "http://southpeak.github.io/atom.xml", ""),
    ("", "刘坤的技术博客", "http://blog.cnbluebox.com/atom.xml", ""),
    ("", "Glow技术团队博客", "http://tech.glowing.com/cn/atom.xml", ""),
    ("", "BestSwifter", "http://bestswifter.com/atom.xml", ""),
    ("", "SwiftGG翻译组", "http://swift.gg/feed.xml", ""),
    ("", "WeRead团队博客", "http://wereadteam.github.io/atom.xml", ""),
    ("", "滴滴技术团队", "http://didi.github.io/atom.xml", ""),
    ("", "微信终端研发中心", "http://dev.qq.com/topic/578a9eb0f15a4f4022d0d1db", ""),
    ("", "limboy无网不剩", "http://limboy.me/atom.xml", ""),
    ("", "卖鱼的程序员", "http://blog.sunnyxx.com/atom.xml", ""),
    ("", "bang's blog", "http://blog.cnbang.net/feed/", ""),
    ("", "ibireme的博客", "http://blog.ibireme.com/feed/", ""),
    ("", "Kitten 的时间胶囊", "http://kittenyang.com/atom.xml", ""),
    ("", "nixzhu的技术博客", "http://nixzhu.github.io/atom.xml", ""),
    ("", "Halfrost's Field", "https://halfrost.com/atom.xml", ""),
    ("", "美团点评技术团队", "http://tech.meituan.com/feed/", ""),
    ("", "AlloyTeam", "http://www.alloyteam.com/feed/", ""),
    ("", "张鑫旭-鑫空间-鑫生活", "http://www.zhangxinxu.com/wordpress/feed/", ""),
    ("", "mobibrw.com", "https://mobibrw.com/feed", ""),
    ("", "唐巧的技术博客", "http://blog.devtang.com/atom.xml", ""),
    ("", "Leo's Blog", "http://leohxj.github.io/atom.xml", ""),
    ("", "喵神@onevcat", "https://onevcat.com/feed.xml", ""),
    ("", "Kyle's Programming Blog", "http://kylezhao.github.io/atom.xml", ""),
    ("", "nianxi", "http://nianxi.net/atom.xml", ""),
    ("", "随机漫步的傻瓜", "http://fancyoung.com/atom.xml", ""),
    ("", "sunnyxx的面试刷题笔记", "http://blog.sunnyxx.com/atom.xml", ""),
    ("", "伯乐在线", "http://blog.jobbole.com/feed/", ""),
    ("", "冰霜之地", "http://www.ifelseif.cn/?feed=rss2", ""),
    ("", "纯净的天空", "http://www.voidcn.com/blog/rss.xml", ""),
    # ── folder: 博客 ─────────────────────────────────────────────────────────
    ("博客", "阮一峰的网络日志", "http://www.ruanyifeng.com/blog/atom.xml", "http://www.ruanyifeng.com/blog"),
    ("博客", "王垠的博客", "http://www.yinwang.org/rss.xml", ""),
    ("博客", "月光博客", "http://www.williamlong.info/rss.xml", "http://williamlong.info/"),
    ("博客", "池建强的MacTalk", "http://macshuo.com/?feed=rss2", ""),
    ("博客", "道哥的黑板报", "http://taosay.net/?feed=rss2", ""),
    ("博客", "Fenng / Dbanotes", "http://dbanotes.net/feed", ""),
    ("博客", "Livid / Bruce", "http://livid.v2ex.com/feed.xml", ""),
    ("博客", "西乔 / 神秘的程序员们", "http://feeds.feedburner.com/mystuff", ""),
    ("博客", "老赵点滴", "http://blog.zhaojie.me/feed.xml", ""),
    ("博客", "酷壳 CoolShell", "http://coolshell.cn/feed", ""),
    ("博客", "云风的 BLOG", "http://blog.codingnow.com/atom.xml", ""),
    ("博客", "美丽的代码", "http://lucida.me/atom.xml", ""),
    ("博客", "峰云就她了", "http://xiaorui.cc/feed/", ""),
    ("博客", "小土刀的博客", "http://wdxtub.com/atom.xml", ""),
    ("博客", "编程珠玑", "http://www.the5fire.com/atom.xml", ""),
    ("博客", "Ken Zhang", "http://kenzhang.cn/feed/", ""),
    ("博客", "MacTalk-池建强的随想录", "http://macshuo.com/?feed=rss2", ""),
    ("博客", "侧边", "http://www.cebian.me/feed/", ""),
    ("博客", "蒸发、升华或消散", "http://wangjunliang.com/feed/", ""),
    ("博客", "小惡魔 – 電腦技術 – 工作筆記 – AppleBOY", "https://blog.wu-boy.com/feed/", ""),
    ("博客", "小王子的探险", "http://blog.lujun9972.win/atom.xml", ""),
    ("博客", "程序师", "http://www.techug.com/feed", ""),
    ("博客", "李开复", "http://blog.sina.com.cn/rss/kaifulee.xml", ""),
    ("博客", "圆心的博客", "http://blog.yanjunzi.com/feed/", ""),
    ("博客", "陈皓 — 酷壳", "http://coolshell.cn/feed", ""),
    ("博客", "代码农场", "http://www.r9it.com/feed.xml", ""),
    ("博客", "林枫的博客", "http://linfan.info/blog/atom.xml", ""),
    ("博客", "淡然", "http://wudaijun.com/atom.xml", ""),
    ("博客", "Jianshu", "https://www.jianshu.com/rss", ""),
    ("博客", "土司.cn", "http://tuzix.cn/feed/", ""),
    ("博客", "酒石酸菌", "http://tartaric-acid.me/atom.xml", ""),
    ("博客", "byvoid", "http://www.byvoid.com/zht/feed", ""),
    ("博客", "Fenng 冯大辉", "https://medium.com/feed/@fenng", ""),
    ("博客", "虫叔", "http://maoao530.github.io/atom.xml", ""),
    ("博客", "不成熟的笔记", "http://semaphoreci.com/blog/feed.xml", ""),
    ("博客", "kenshin", "http://www.jianshu.com/users/kenshin/latest_articles?format=atom", ""),
    ("博客", "博客园 - 推荐", "http://www.cnblogs.com/aggsite/SiteRss", ""),
    ("博客", "博客园 - 精华", "http://feed.cnblogs.com/blog/sitehome/rss", ""),
    ("博客", "Piasy Blog", "http://blog.piasy.com/atom.xml", ""),
    ("博客", "卢克的博客", "https://lukeai.github.io/atom.xml", ""),
    ("博客", "大彻大悟的程序人生", "http://blog.atime.me/atom.xml", ""),
    ("博客", "小猪的博客", "http://www.qinshaoxuan.cn/feed/", ""),
    ("博客", "Vamei", "http://www.cnblogs.com/vamei/rss", ""),
    ("博客", "码农周刊", "http://weekly.manong.io/issues.rss", ""),
    ("博客", "Waylau", "http://waylau.com/atom.xml", ""),
    ("博客", "小小空", "http://blog.xiaoxk.com/atom.xml", ""),
    ("博客", "Cuttlefish's Island", "http://cuttlefish.island.wordpress.com/feed/", ""),
    ("博客", "Teahour.fm", "http://teahour.fm/feed.xml", ""),
    ("博客", "Segmentfault原创", "https://segmentfault.com/rss/original", ""),
    ("博客", "开发技术前线", "http://www.devtf.cn/?feed=rss2", ""),
    ("博客", "draveness的博客", "https://draveness.me/feed.xml", ""),
    ("博客", "一个果壳打滚的人", "http://zhouyichu.com/atom.xml", ""),
    ("博客", "博客", "https://mengkang.net/feed.xml", ""),
    ("博客", "思维杂货店", "http://jianshu.io/p/97ed7a36dd70/rss", ""),
    ("博客", "caoz的梦呓 - 博客园", "http://www.cnblogs.com/caozhiwei/rss", ""),
    ("博客", "二环外码农", "http://blog.ityouknow.com/feed.xml", ""),
    ("博客", "吴鹏煜的博客", "http://wupengyu.cn/feed/", ""),
    ("博客", "卧龙岗上的码农", "http://www.cnblogs.com/fishpro/rss", ""),
    ("博客", "时评员", "http://blog.huatai.me/atom.xml", ""),
    ("博客", "一路向北", "http://blog.liangruijia.cn/atom.xml", ""),
    ("博客", "苍耳之博客", "http://wangyuechao.com/atom.xml", ""),
    ("博客", "迈克尔乔丹", "http://blog.3m-x.cn/atom.xml", ""),
    ("博客", "搞机工坊", "http://www.gaojigongfang.com/feed", ""),
    ("博客", "Kiwi's Garden", "http://blog.kiwi.zl.is/atom.xml", ""),
    ("博客", "Beipy", "http://www.beipy.com/feed/", ""),
    ("博客", "技术派", "http://www.techupdate.cn/feed.xml", ""),
    ("博客", "互联网人的日常", "http://www.javazhiyin.com/feed", ""),
    ("博客", "四平八稳", "http://www.sipingbawen.com/feed/", ""),
    ("博客", "博客 – Tao of Mac", "https://taoofmac.com/space/blog/feed/", ""),
    ("博客", "阿里技术", "https://102.alibaba.com/newsDetail.do?news.newsId=105", ""),
    ("博客", "掘金 -- 博客", "https://juejin.im/rss", ""),
    ("博客", "微信读书技术博客", "http://wereadteam.github.io/atom.xml", ""),
    ("博客", "UED Team", "http://taobaofed.org/atom.xml", ""),
    ("博客", "前端早读课", "http://www.zaoduke.net/feed/", ""),
    ("博客", "百度前端研发部FEX", "http://fex.baidu.com/feed.xml", ""),
    ("博客", "腾讯 AlloyTeam", "http://www.alloyteam.com/feed/", ""),
    ("博客", "Facebook 工程团队", "https://engineering.fb.com/feed/", ""),
    ("博客", "Twitter Engineering", "https://blog.twitter.com/engineering/en_us/blog.rss", ""),
    ("博客", "Netflix Tech Blog", "https://netflixtechblog.com/feed", ""),
    ("博客", "LinkedIn Engineering", "https://engineering.linkedin.com/blog.rss", ""),
    ("博客", "Dropbox Tech Blog", "https://dropbox.tech/feed", ""),
    ("博客", "Stripe Blog", "https://stripe.com/blog/feed.rss", ""),
    ("博客", "Slack Engineering", "https://slack.engineering/feed", ""),
    ("博客", "Uber Engineering", "https://eng.uber.com/feed/", ""),
    ("博客", "Pinterest Engineering", "https://medium.com/feed/pinterest-engineering", ""),
    ("博客", "Spotify Engineering", "https://engineering.atspotify.com/feed/", ""),
    ("博客", "Amazon Science", "https://www.amazon.science/index.rss", ""),
    ("博客", "Microsoft Research Blog", "https://www.microsoft.com/en-us/research/feed/", ""),
    ("博客", "Google Research Blog", "http://googleresearch.blogspot.com/atom.xml", ""),
    ("博客", "DeepMind Blog", "https://www.deepmind.com/blog/rss.xml", ""),
    ("博客", "OpenAI Blog", "https://openai.com/blog/rss/", ""),
    # ── folder: reference ────────────────────────────────────────────────────
    ("reference", "MDN Web Docs", "https://developer.mozilla.org/en-US/docs/feeds/rss/", ""),
    ("reference", "Stack Overflow", "https://stackoverflow.com/feeds", ""),
    ("reference", "DevDocs", "https://devdocs.io/news.atom", ""),
    ("reference", "CSS-Tricks", "https://css-tricks.com/feed/", ""),
    ("reference", "Smashing Magazine", "https://www.smashingmagazine.com/feed/", ""),
    ("reference", "A List Apart", "https://alistapart.com/main/feed/", ""),
    ("reference", "CodePen Blog", "https://blog.codepen.io/feed/", ""),
    ("reference", "Web.dev", "https://web.dev/feed.xml", ""),
    # ── folder: gatecse ──────────────────────────────────────────────────────
    ("gatecse", "Gate2015", "http://gate2015.info/?feed=rss2", ""),
    # ── folder: 临时 ─────────────────────────────────────────────────────────
    ("临时", "Hacker News", "https://news.ycombinator.com/rss", ""),
    ("临时", "Lobsters", "https://lobste.rs/rss", ""),
    ("临时", "Echo JS", "http://www.echojs.com/rss", ""),
    ("临时", "Frontend Weekly", "http://frontendweekly.co/rss/", ""),
    ("临时", "JavaScript Weekly", "http://javascriptweekly.com/rss", ""),
    ("临时", "Node Weekly", "http://nodeweekly.com/rss", ""),
    ("临时", "Python Weekly", "http://www.pythonweekly.com/rss/pyweekly.xml", ""),
    ("临时", "Ruby Weekly", "http://rubyweekly.com/rss", ""),
    ("临时", "StatusCode Weekly", "http://weekly.statuscode.com/rss", ""),
    ("临时", "Golang Weekly", "https://golangweekly.com/rss", ""),
    ("临时", "Database Weekly", "https://dbweekly.com/rss", ""),
    ("临时", "Postgres Weekly", "https://postgresweekly.com/rss", ""),
    ("临时", "Docker Weekly", "https://www.docker.com/newsletter-subscription", ""),
    ("临时", "Serverless Weekly", "https://serverless.email/issues.rss", ""),
    ("临时", "Hacker Newsletter", "http://www.hackernewsletter.com/rss", ""),
    ("临时", "O'Reilly Radar", "http://radar.oreilly.com/atom.xml", ""),
    ("临时", "ACM Queue", "http://queue.acm.org/rss.cfm", ""),
    ("临时", "InfoQ", "http://www.infoq.com/rss/rss.action", ""),
    ("临时", "IBM developerWorks", "http://www.ibm.com/developerworks/mydeveloperworks/blogs/roller-ui/rendering/feed/javaone_articles/rss?lang=en", ""),
    ("临时", "DZone", "https://dzone.com/feeds/frontpage.rss", ""),
    ("临时", "Pony Foo", "https://ponyfoo.com/feed/authoritative.xml", ""),
    ("临时", "2ality", "http://www.2ality.com/feeds/posts/default", ""),
    ("临时", "Axel Rauschmayer", "https://2ality.com/feeds/posts/default", ""),
    ("临时", "Ariya Hidayat", "http://ariya.ofilabs.com/feed", ""),
    ("临时", "Addy Osmani", "http://addyosmani.com/blog/feed/", ""),
    ("临时", "Nicholas C. Zakas", "https://humanwhocodes.com/feeds/blog.xml", ""),
    ("临时", "John Resig", "http://ejohn.org/blog/feed/", ""),
    ("临时", "Paul Irish", "http://paulirish.com/feed/", ""),
    ("临时", "David Walsh Blog", "https://davidwalsh.name/feed", ""),
    ("临时", "Wes Bos", "http://wesbos.com/rss/", ""),
    ("临时", "Scotch.io", "https://scotch.io/feed", ""),
    ("临时", "Alligator.io", "https://alligator.io/rss.xml", ""),
    ("临时", "Robin Wieruch", "https://www.robinwieruch.de/index.xml", ""),
    ("临时", "Dan Abramov", "https://overreacted.io/rss.xml", ""),
    ("临时", "kentcdodds", "https://kentcdodds.com/blog/rss.xml", ""),
    ("临时", "Jake Archibald", "https://jakearchibald.com/atom.xml", ""),
    ("临时", "Surma (surma.dev)", "https://surma.dev/feed.xml", ""),
    ("临时", "The 8-Bit Archaeology", "http://www.digibarn.com/collections/newsletters/byte/BYTE-1975-11/index.html", ""),
    ("临时", "Yan Cui", "http://theburningmonk.com/feed/", ""),
    ("临时", "Cindy Sridharan", "https://medium.com/feed/@copyconstruct", ""),
    ("临时", "程序员的那些事", "http://javaeeee.iteye.com/rss", ""),
    ("临时", "Thoughtworks Insights", "https://www.thoughtworks.com/rss/insights.xml", ""),
    ("临时", "Martin Fowler", "https://martinfowler.com/feed.atom", ""),
    ("临时", "Sam Newman", "http://samnewman.io/blog/feed.xml", ""),
    ("临时", "Brendan Gregg", "http://www.brendangregg.com/blog/rss.xml", ""),
    ("临时", "High Scalability", "http://feeds.feedburner.com/HighScalability", ""),
    ("临时", "The Morning Paper", "https://blog.acolyer.org/feed/", ""),
    # ── folder: blog ─────────────────────────────────────────────────────────
    ("blog", "Joel on Software", "https://www.joelonsoftware.com/feed/", ""),
    ("blog", "Paul Graham", "http://www.paulgraham.com/rss.html", ""),
    ("blog", "Signal v. Noise", "https://m.signalvnoise.com/feed/", ""),
    ("blog", "Seth Godin's Blog", "http://feeds.feedblitz.com/sethsblog", ""),
    ("blog", "Ben Evans", "https://www.ben-evans.com/benedictevans/feed.rss", ""),
    ("blog", "Benedict Evans", "https://www.ben-evans.com/benedictevans/rss.xml", ""),
    ("blog", "Wait But Why", "https://waitbutwhy.com/feed", ""),
    ("blog", "Derek Sivers", "https://sive.rs/en.atom", ""),
    ("blog", "Stratechery", "https://stratechery.com/feed/", ""),
    ("blog", "Cal Newport", "https://www.calnewport.com/blog/feed/", ""),
    ("blog", "Clay Christensen", "http://www.claytonchristensen.com/feed/", ""),
    ("blog", "Naval Ravikant", "https://nav.al/rss", ""),
    # ── folder: life ─────────────────────────────────────────────────────────
    ("life", "心理月刊", "http://www.psychologies.com.cn/rss/index.xml", ""),
    ("life", "好奇心日报", "http://www.qdaily.com/feed.xml", ""),
    ("life", "少数派", "http://sspai.com/feed", ""),
    # ── folder: SegmentFault ─────────────────────────────────────────────────
    ("SegmentFault", "SegmentFault 思否", "https://segmentfault.com/feeds", ""),
    ("SegmentFault", "SegmentFault 专栏精选", "https://segmentfault.com/rss/selected", ""),
    ("SegmentFault", "SegmentFault 问答", "https://segmentfault.com/rss/questions", ""),
    # ── folder: github ───────────────────────────────────────────────────────
    ("github", "GitHub Blog", "https://github.blog/feed/", ""),
    ("github", "GitHub Engineering", "https://githubengineering.com/atom.xml", ""),
    ("github", "GitHub Changelog", "https://github.blog/changelog/feed/", ""),
    ("github", "GitHub Actions", "https://github.blog/feed/?cat=product", ""),
    ("github", "Git Tips", "http://gitready.com/atom.xml", ""),
    ("github", "Pro Git", "http://git-scm.com/blog/feed.xml", ""),
    ("github", "GitLab Blog", "https://about.gitlab.com/blog/feed.xml", ""),
    ("github", "try.github.io", "http://try.github.io/rss", ""),
    ("github", "GitHub Explore", "https://github.com/explore.atom", ""),
    # ── folder: 问答 ─────────────────────────────────────────────────────────
    ("问答", "StackOverflow Questions", "https://stackoverflow.com/questions/feed", ""),
    ("问答", "Server Fault", "https://serverfault.com/questions/feed", ""),
    # ── folder: 必读 ─────────────────────────────────────────────────────────
    ("必读", "Paul Graham Essays", "http://www.paulgraham.com/articles.html", ""),
    ("必读", "The Changelog", "https://changelog.com/feed", ""),
    ("必读", "Hacker News Best", "https://hnrss.org/best", ""),
    ("必读", "Hacker News Front Page", "https://hnrss.org/frontpage", ""),
    ("必读", "TLDR Newsletter", "https://tldr.tech/rss", ""),
    ("必读", "Programming Digest", "https://programmingdigest.net/digests.rss", ""),
    ("必读", "Pointer", "https://www.pointer.io/rss/", ""),
    ("必读", "SRE Weekly", "https://sreweekly.com/feed/", ""),
    ("必读", "Software Lead Weekly", "http://softwareleadweekly.com/issues.rss", ""),
    ("必读", "Increment Magazine", "https://increment.com/feed.xml", ""),
    ("必读", "ACM TechNews", "http://technews.acm.org/", ""),
    ("必读", "IEEE Spectrum Technology", "https://spectrum.ieee.org/rss/technology/fulltext", ""),
    ("必读", "MIT News - Computer Science", "https://news.mit.edu/rss/topic/computers", ""),
    ("必读", "Stanford AI Lab Blog", "http://ai.stanford.edu/blog/feed.xml", ""),
    ("必读", "The Pragmatic Engineer", "https://blog.pragmaticengineer.com/rss/", ""),
    ("必读", "levelup.gitconnected.com", "https://levelup.gitconnected.com/feed", ""),
    # ── folder: 文档 ─────────────────────────────────────────────────────────
    ("文档", "MDN Blog", "https://hacks.mozilla.org/feed/", ""),
    # ── folder: T.L ──────────────────────────────────────────────────────────
    ("T.L", "Tech Lead Journal", "https://techleadjournal.dev/index.xml", ""),
    ("T.L", "The Pragmatic Engineer Newsletter", "https://newsletter.pragmaticengineer.com/feed", ""),
    ("T.L", "LeadDev", "https://leaddev.com/feed", ""),
    ("T.L", "StaffEng", "https://staffeng.com/feed", ""),
    ("T.L", "Engineering Management Weekly", "https://engineeringmanagementweekly.substack.com/feed", ""),
    ("T.L", "Lara Hogan", "https://larahogan.me/blog/feed/", ""),
    ("T.L", "Software Engineering Daily", "https://softwareengineeringdaily.com/feed/", ""),
    ("T.L", "CTO Craft", "https://ctocraft.com/blog/feed", ""),
    ("T.L", "Pat Kua", "https://www.patkua.com/blog/feed/", ""),
    ("T.L", "Camille Fournier", "https://www.elidedbranches.com/feeds/posts/default", ""),
    ("T.L", "Charity Majors", "https://charity.wtf/feed/", ""),
    ("T.L", "Rands in Repose", "https://randsinrepose.com/feed/", ""),
    ("T.L", "Will Larson", "https://lethain.com/feeds/", ""),
    ("T.L", "First Round Review", "https://review.firstround.com/feed", ""),
    ("T.L", "Manager's Playbook", "https://managersplaybook.substack.com/feed", ""),
    ("T.L", "The Engineering Manager", "https://www.theengineeringmanager.com/feed/", ""),
    ("T.L", "Software at Scale", "https://www.softwareatscale.dev/feed", ""),
    ("T.L", "Systems Thinking", "https://systemsthinking.substack.com/feed", ""),
    ("T.L", "Increment", "https://increment.com/feed.xml", ""),
    ("T.L", "ACM Queue Blog", "https://queue.acm.org/rss_feed.cfm", ""),
    ("T.L", "InfoQ Architecture", "https://www.infoq.com/architecture-design/rss/", ""),
    ("T.L", "Netflix Technology Blog", "https://netflixtechblog.com/feed", ""),
    ("T.L", "Discord Engineering", "https://discord.com/blog/rss.xml", ""),
    ("T.L", "Figma Engineering", "https://www.figma.com/blog/feed/", ""),
    ("T.L", "Shopify Engineering", "https://shopify.engineering/blog.atom", ""),
    ("T.L", "Airbnb Engineering", "https://medium.com/feed/airbnb-engineering", ""),
    ("T.L", "Lyft Engineering", "https://eng.lyft.com/feed", ""),
    ("T.L", "Cloudflare Blog", "https://blog.cloudflare.com/rss/", ""),
    ("T.L", "HashiCorp Blog", "https://www.hashicorp.com/blog/feed.xml", ""),
    ("T.L", "Kubernetes Blog", "https://kubernetes.io/feed.xml", ""),
    ("T.L", "Docker Blog", "https://www.docker.com/blog/feed/", ""),
    ("T.L", "AWS Architecture Blog", "https://aws.amazon.com/blogs/architecture/feed/", ""),
    ("T.L", "Google Cloud Architecture Blog", "https://cloud.google.com/blog/products/gcp/rss", ""),
    ("T.L", "Azure Architecture Blog", "https://devblogs.microsoft.com/azure-architecture/feed/", ""),
    # ── folder: 站点 ─────────────────────────────────────────────────────────
    ("站点", "V2EX", "https://www.v2ex.com/index.xml", ""),
    ("站点", "SegmentFault", "https://segmentfault.com/feeds", ""),
    ("站点", "开源中国", "https://www.oschina.net/news/rss", ""),
    ("站点", "博客园", "https://feed.cnblogs.com/blog/sitehome/rss", ""),
    ("站点", "51CTO博客", "http://blog.51cto.com/rss.php", ""),
    ("站点", "CSDN", "http://www.csdn.net/rss/news_tech.do", ""),
    ("站点", "ITEYE", "http://feed.iteye.com/blog/rss", ""),
    # ── folder: google ───────────────────────────────────────────────────────
    ("google", "Google Developers Blog", "https://developers.googleblog.com/feeds/posts/default", ""),
    ("google", "Google Cloud Blog", "https://cloud.google.com/blog/rss/", ""),
    # ── folder: It ───────────────────────────────────────────────────────────
    ("It", "TechCrunch", "https://techcrunch.com/feed/", ""),
    ("It", "The Verge", "https://www.theverge.com/rss/index.xml", ""),
    ("It", "Ars Technica", "http://feeds.arstechnica.com/arstechnica/index", ""),
    ("It", "Engadget", "https://www.engadget.com/rss.xml", ""),
    ("It", "Gizmodo", "https://gizmodo.com/rss", ""),
    ("It", "Wired", "https://www.wired.com/feed/rss", ""),
    ("It", "MIT Technology Review", "https://www.technologyreview.com/feed/", ""),
    ("It", "VentureBeat", "https://venturebeat.com/feed/", ""),
    ("It", "ReadWrite", "http://readwrite.com/feed/", ""),
    ("It", "Mashable Tech", "http://feeds.mashable.com/mashable/tech", ""),
    ("It", "Fast Company", "https://www.fastcompany.com/latest/rss?format=xml", ""),
    ("It", "The Information", "https://www.theinformation.com/feed", ""),
    ("It", "Protocol", "https://www.protocol.com/feed", ""),
    ("It", "Morning Brew", "https://www.morningbrew.com/daily/issues.rss", ""),
    # ── folder: 日报 ─────────────────────────────────────────────────────────
    ("日报", "知乎日报", "https://rsshub.app/zhihu/daily", ""),
    ("日报", "湾区日报", "https://wanqu.co/feed.json", ""),
    ("日报", "科技爱好者周刊", "https://feeds2.feedburner.com/ruanyifeng", ""),
    ("日报", "Hacker News Daily", "https://www.daemonology.net/hn-daily/index.rss", ""),
    ("日报", "Reddit Programming", "https://www.reddit.com/r/programming/.rss", ""),
    ("日报", "Reddit Technology", "https://www.reddit.com/r/technology/.rss", ""),
    ("日报", "Reddit WebDev", "https://www.reddit.com/r/webdev/.rss", ""),
    ("日报", "Dev.to", "https://dev.to/feed", ""),
    ("日报", "Hashnode", "https://hashnode.com/rss", ""),
    ("日报", "Medium – Programming", "https://medium.com/feed/topic/programming", ""),
    ("日报", "DailyDev", "https://app.daily.dev/rss", ""),
    ("日报", "Sidebar.io", "https://sidebar.io/feed.xml", ""),
    # ── folder: Docker ───────────────────────────────────────────────────────
    ("Docker", "Docker Blog", "https://www.docker.com/blog/feed/", ""),
    ("Docker", "Docker Hub", "https://hub.docker.com/search?q=&type=image", ""),
    # ── folder: ios ──────────────────────────────────────────────────────────
    ("ios", "NSHipster", "https://nshipster.com/feed.xml", ""),
    ("ios", "Swift by Sundell", "https://www.swiftbysundell.com/feed.rss", ""),
    ("ios", "SwiftRocks", "https://swiftrocks.com/rss.xml", ""),
    ("ios", "Ole Begemann", "https://oleb.net/blog/atom.xml", ""),
    ("ios", "iOS Dev Weekly", "https://iosdevweekly.com/issues.rss", ""),
    ("ios", "AppCoda", "https://www.appcoda.com/feed/", ""),
    ("ios", "raywenderlich.com", "https://www.raywenderlich.com/feed", ""),
    ("ios", "Natasha The Robot", "https://www.natashatherobot.com/feed/", ""),
    ("ios", "objc.io", "https://www.objc.io/feed.xml", ""),
    ("ios", "Cocoa with Love", "https://cocoawithlove.com/feed.xml", ""),
    ("ios", "inessential", "https://inessential.com/xml/rss.xml", ""),
    ("ios", "Daring Fireball", "https://daringfireball.net/feeds/main", ""),
    ("ios", "Marco Arment", "https://marco.org/rss", ""),
    ("ios", "One Foot Tsunami", "https://onefoottsunami.com/feed/", ""),
    ("ios", "Stratechery", "https://stratechery.com/feed/", ""),
    ("ios", "Six Colors", "https://sixcolors.com/feed/", ""),
    ("ios", "MacStories", "https://www.macstories.net/feed/", ""),
    ("ios", "512 Pixels", "https://512pixels.net/feed/", ""),
    ("ios", "Apple Developer News", "https://developer.apple.com/news/rss/news.rss", ""),
    ("ios", "Swift Forums", "https://forums.swift.org/latest.rss", ""),
    ("ios", "Hacking with Swift", "https://www.hackingwithswift.com/articles/rss", ""),
    ("ios", "Swift Algorithms", "https://swift.org/blog/index.xml", ""),
    ("ios", "Point-Free", "https://www.pointfree.co/feed", ""),
    ("ios", "Swift Weekly Brief", "https://swiftweeklybrief.com/feed.xml", ""),
    ("ios", "little bites of cocoa", "https://littlebitesofcocoa.com/rss", ""),
    ("ios", "Use Your Loaf", "https://useyourloaf.com/blog/rss.xml", ""),
    ("ios", "Donny Wals", "https://www.donnywals.com/feed/", ""),
    ("ios", "Antoine van der Lee", "https://www.avanderlee.com/feed/", ""),
    # ── folder: Sketch ───────────────────────────────────────────────────────
    ("Sketch", "Sketch Blog", "https://www.sketch.com/blog/feed.xml", ""),
    ("Sketch", "Sketch App Sources", "https://www.sketchappsources.com/feed.rss", ""),
    # ── folder: Daily Read ───────────────────────────────────────────────────
    ("Daily Read", "Morning Brew Tech", "https://www.morningbrew.com/emerging-tech/issues.rss", ""),
    # ── folder: Product Design ───────────────────────────────────────────────
    ("Product Design", "Nielsen Norman Group", "https://www.nngroup.com/feed/rss/", ""),
    ("Product Design", "UX Collective", "https://uxdesign.cc/feed", ""),
    # ── folder: Programming ──────────────────────────────────────────────────
    ("Programming", "The Morning Paper", "https://blog.acolyer.org/feed/", ""),
    ("Programming", "High Scalability", "http://feeds.feedburner.com/HighScalability", ""),
    ("Programming", "Brendan Gregg", "http://www.brendangregg.com/blog/rss.xml", ""),
    ("Programming", "Martin Fowler", "https://martinfowler.com/feed.atom", ""),
    ("Programming", "Joel on Software", "https://www.joelonsoftware.com/feed/", ""),
    ("Programming", "Coding Horror", "https://blog.codinghorror.com/rss/", ""),
    ("Programming", "The Old New Thing", "https://devblogs.microsoft.com/oldnewthing/feed", ""),
    ("Programming", "Eric Lippert", "https://ericlippert.com/feed/", ""),
    ("Programming", "The Clean Coder", "https://blog.cleancoder.com/feed.xml", ""),
    ("Programming", "Robert C. Martin (Uncle Bob)", "https://blog.cleancoder.com/feed.xml", ""),
    ("Programming", "Dan Luu", "https://danluu.com/atom.xml", ""),
    ("Programming", "Aphyr (Kyle Kingsbury)", "https://aphyr.com/feed", ""),
    ("Programming", "Marc Brooker", "https://brooker.co.za/blog/rss.xml", ""),
    ("Programming", "Basecs", "https://medium.com/feed/basecs", ""),
    ("Programming", "Julia Evans", "https://jvns.ca/atom.xml", ""),
    ("Programming", "Destroy All Software", "https://www.destroyallsoftware.com/blog.atom", ""),
    ("Programming", "Hillel Wayne", "https://www.hillelwayne.com/post/index.xml", ""),
    ("Programming", "Fabulous Adventures in Coding", "https://ericlippert.com/feed/", ""),
    ("Programming", "Fabulous Adventures Eric Lippert", "https://ericlippert.com/feed/", ""),
    ("Programming", "Lambda the Ultimate", "http://lambda-the-ultimate.org/rss.xml", ""),
    ("Programming", "SIGPLAN Notices", "http://cacm.acm.org/rss", ""),
    ("Programming", "Tomas Petricek", "http://tomasp.net/rss.aspx", ""),
    ("Programming", "Andreas Kling", "https://awesomekling.github.io/feed.xml", ""),
    ("Programming", "Performance Matters", "https://www.cs.cornell.edu/~asampson/blog/feed.xml", ""),
    ("Programming", "John Carmack (Inlined)", "http://the-witness.net/news/feed/", ""),
    ("Programming", "David Beazley", "http://www.dabeaz.com/blog/feed.xml", ""),
    ("Programming", "Eli Bendersky's website", "https://eli.thegreenplace.net/feeds/all.atom.xml", ""),
    ("Programming", "Amos Wenger (fasterthanlime)", "https://fasterthanli.me/index.xml", ""),
    ("Programming", "Armin Ronacher", "https://lucumr.pocoo.org/feed.atom", ""),
    ("Programming", "Raymond Hettinger", "https://rhettinger.wordpress.com/feed/", ""),
    ("Programming", "Ned Batchelder", "https://nedbatchelder.com/blog/rss.xml", ""),
    ("Programming", "tef (without a name)", "https://programmingisterrible.com/rss", ""),
    ("Programming", "Coding for SSDs", "http://codecapsule.com/feed/", ""),
    ("Programming", "Fabrice Bellard", "https://www.bellard.org/rss/index.rss", ""),
    ("Programming", "Peter Norvig", "http://norvig.com/rss-feed.xml", ""),
    ("Programming", "Mike Acton", "https://macton.medium.com/feed", ""),
    ("Programming", "The Rust Blog", "https://blog.rust-lang.org/feed.xml", ""),
    ("Programming", "Go Blog", "https://blog.golang.org/feed.atom", ""),
    ("Programming", "Python Insider", "https://feeds.feedburner.com/PythonInsider", ""),
    ("Programming", "OCaml Planet", "https://v2.ocaml.org/community/planet/", ""),
    ("Programming", "Haskell Weekly", "https://haskellweekly.news/newsletter.atom", ""),
    ("Programming", "Planet Clojure", "http://planet.clojure.in/atom.xml", ""),
    ("Programming", "Elixir Radar", "https://elixir-radar.com/issues.rss", ""),
    ("Programming", "Scala Times", "https://scalatimes.com/feed/", ""),
    ("Programming", "This Week in Rust", "https://this-week-in-rust.org/rss.xml", ""),
    ("Programming", "JavaScript Weekly", "https://javascriptweekly.com/rss", ""),
    ("Programming", "Node Weekly", "https://nodeweekly.com/rss", ""),
    ("Programming", "CSS Weekly", "https://css-weekly.com/feed/", ""),
    ("Programming", "Frontend Focus", "https://frontendfoc.us/rss", ""),
    ("Programming", "Vue.js News", "https://news.vuejs.org/feed.xml", ""),
    ("Programming", "React Status", "https://react.statuscode.com/rss", ""),
    ("Programming", "TypeScript Weekly", "https://typescript-weekly.com/issues.rss", ""),
    ("Programming", "PyCoder's Weekly", "https://pycoders.com/issues/rss", ""),
    ("Programming", "Real Python", "https://realpython.com/atom.xml", ""),
    ("Programming", "Full Stack Python", "https://www.fullstackpython.com/feed.atom", ""),
    ("Programming", "Planet Python", "https://planetpython.org/rss20.xml", ""),
    ("Programming", "Towards Data Science", "https://towardsdatascience.com/feed", ""),
    ("Programming", "Two Minute Papers", "https://www.youtube.com/feeds/videos.xml?user=keeroyz", ""),
    ("Programming", "Papers We Love", "https://paperswelove.org/feed.xml", ""),
    ("Programming", "The Morning Paper (Adrian Colyer)", "https://blog.acolyer.org/feed/", ""),
    ("Programming", "ACM SIGPLAN", "https://dl.acm.org/action/showFeed?ui=rss&rss=dl", ""),
    ("Programming", "USENIX ;login:", "https://www.usenix.org/publications/loginonline/rss.xml", ""),
    ("Programming", "IEEE Software", "http://ieeexplore.ieee.org/rss/TOC4.XML", ""),
    ("Programming", "Communications of the ACM", "https://dl.acm.org/citation.cfm?id=J79&type=periodical&Feed=rss&element=periodical", ""),
    ("Programming", "Docker Blog", "https://www.docker.com/blog/feed/", ""),
    ("Programming", "Kubernetes Blog", "https://kubernetes.io/feed.xml", ""),
    ("Programming", "CNCF Blog", "https://www.cncf.io/blog/feed/", ""),
    ("Programming", "HashiCorp Blog", "https://www.hashicorp.com/blog/feed.xml", ""),
    ("Programming", "Terraform Blog", "https://www.hashicorp.com/blog/products/terraform/feed", ""),
    ("Programming", "Packer Blog", "https://www.packer.io/blog/feed.xml", ""),
    ("Programming", "Ansible Blog", "https://www.ansible.com/blog/rss.xml", ""),
    ("Programming", "Netflix Tech Blog", "https://netflixtechblog.com/feed", ""),
    ("Programming", "Airbnb Engineering", "https://medium.com/feed/airbnb-engineering", ""),
    ("Programming", "Uber Engineering", "https://eng.uber.com/feed/", ""),
    ("Programming", "Lyft Engineering", "https://eng.lyft.com/feed", ""),
    ("Programming", "Dropbox Tech", "https://dropbox.tech/feed", ""),
    ("Programming", "Spotify Engineering", "https://engineering.atspotify.com/feed/", ""),
    ("Programming", "Twitter Engineering", "https://blog.twitter.com/engineering/en_us/blog.rss", ""),
    ("Programming", "LinkedIn Engineering", "https://engineering.linkedin.com/blog.rss", ""),
    ("Programming", "Stripe Engineering", "https://stripe.com/blog/feed.rss", ""),
    ("Programming", "Slack Engineering", "https://slack.engineering/feed", ""),
    ("Programming", "Discord Engineering", "https://discord.com/blog/rss.xml", ""),
    ("Programming", "Figma Engineering", "https://www.figma.com/blog/feed/", ""),
    ("Programming", "Shopify Engineering", "https://shopify.engineering/blog.atom", ""),
    ("Programming", "Cloudflare Blog", "https://blog.cloudflare.com/rss/", ""),
    # ── folder: 廖雪峰 ───────────────────────────────────────────────────────
    ("廖雪峰", "廖雪峰的官方网站", "https://www.liaoxuefeng.com/feed.rss", ""),
    # ── folder: 提供订阅的网站 ───────────────────────────────────────────────
    ("提供订阅的网站", "Lobsters", "https://lobste.rs/rss", ""),
    ("提供订阅的网站", "Dev.to", "https://dev.to/feed", ""),
    # ── folder: 安全 ─────────────────────────────────────────────────────────
    ("安全", "Krebs on Security", "https://krebsonsecurity.com/feed/", ""),
    # ── folder: 社区 ─────────────────────────────────────────────────────────
    ("社区", "V2EX", "https://www.v2ex.com/index.xml", ""),
    ("社区", "Lobsters", "https://lobste.rs/rss", ""),
    # ── folder: 工具 ─────────────────────────────────────────────────────────
    ("工具", "The Sweet Setup", "https://thesweetsetup.com/feed/", ""),
    # ── folder: 美食 ─────────────────────────────────────────────────────────
    ("美食", "下厨房精选", "https://www.xiachufang.com/feed/", ""),
    ("美食", "大众点评精选", "https://www.dianping.com/feed/", ""),
    # ── folder: 数学 ─────────────────────────────────────────────────────────
    ("数学", "矩阵67", "https://matrix67.com/blog/feed/", ""),
    ("数学", "Mathbabe", "https://mathbabe.org/feed/", ""),
    ("数学", "Math ∩ Programming", "https://jeremykun.com/feed/", ""),
    ("数学", "Better Explained", "https://betterexplained.com/feed/", ""),
    ("数学", "Terence Tao's Blog", "https://terrytao.wordpress.com/feed/", ""),
    ("数学", "nLab - Recent Changes", "https://nlab-pages.s3.us-east-2.amazonaws.com/nlab/show/HomePage", ""),
    ("数学", "OEIS News", "https://oeis.org/feed.xml", ""),
    ("数学", "ccjou", "https://ccjou.wordpress.com/feed/", ""),
    ("数学", "zhangzujin", "http://www.cnblogs.com/zhangzujin/rss", ""),
]


# =============================================================================
# Category & country mapping
# =============================================================================
FOLDER_TO_CATEGORY: dict[str, str] = {
    "": "blog",
    "博客": "blog",
    "Programming": "programming",
    "ios": "mobile_tech",
    "It": "tech",
    "日报": "tech",
    "站点": "tech",
    "安全": "security",
    "数学": "math",
    "github": "tech",
    "必读": "tech",
    "文档": "tech",
    "T.L": "life",
    "life": "life",
    "美食": "life",
    "Product Design": "design",
    "Sketch": "design",
    "Daily Read": "tech",
    "社区": "community",
    "reference": "reference",
    "问答": "reference",
    "SegmentFault": "community",
    "blog": "blog",
    "临时": "tech",
    "Docker": "tech",
    "google": "tech",
    "gatecse": "reference",
    "廖雪峰": "blog",
    "提供订阅的网站": "tech",
    "工具": "tech",
}

# Patterns for detecting Chinese sources
CN_PATTERNS = [
    r"\.cn[/:]", r"cnblogs\.com", r"csdn\.net", r"sina\.com",
    r"163\.com", r"weibo\.com", r"qq\.com", r"jianshu\.com",
    r"segmentfault\.com", r"v2ex\.com", r"oschina\.net",
    r"51cto\.com", r"iteye\.com", r"cnblogs\.com", r"sspai\.com",
    r"ruanyifeng\.com", r"coolshell\.cn", r"infoq\.com/cn",
    r"juejin\.", r"zhihu\.com", r"36kr\.com", r"huxiu\.com",
    r"ifanr\.com", r"tmtpost\.com", r"qdaily\.com",
    r"williamlong\.info", r"raychase\.net", r"wklken\.me",
    r"codingnow\.com", r"yinwang\.org", r"macshuo\.com",
    r"byvoid\.com", r"lucida\.me", r"qbitai\.com",
    r"liaoxuefeng\.com", r"matrix67\.com",
]

# Titles that indicate Chinese content
CN_TITLE_PATTERNS = [
    "的博客", "的技术", "团队", "日报", "周报", "技术", "中文",
    "阮一峰", "酷壳", "月光", "云风", "程序师", "博客园",
    "掘金", "知乎", "简书", "开源", "中国", "百度", "腾讯",
    "阿里", "美团", "滴滴", "微信", "淘宝", "网易",
]


def detect_country(url: str, title: str) -> str | None:
    """Detect whether a feed is Chinese (CN) or English (EN) based on URL/title."""
    url_lower = url.lower()
    for pattern in CN_PATTERNS:
        if re.search(pattern, url_lower, re.IGNORECASE):
            return "CN"
    for pattern in CN_TITLE_PATTERNS:
        if pattern in title:
            return "CN"
    # Check for obviously English domains
    en_patterns = [
        r"github\.", r"stackoverflow\.", r"mozilla\.", r"google\.",
        r"microsoft\.", r"apple\.", r"medium\.com/feed/@[a-z]",
        r"wordpress\.com", r"blogspot\.com", r"substack\.com",
        r"\.dev/", r"\.io/", r"\.com/feed", r"\.org/feed",
        r"\.net/feed",
    ]
    for pattern in en_patterns:
        if re.search(pattern, url_lower):
            return "EN"
    # Chinese-sounding titles (contains CJK characters)
    if re.search(r"[\u4e00-\u9fff]", title):
        return "CN"
    return "EN"


def get_category_country(folder: str, url: str, title: str) -> tuple[str, str | None]:
    """Map OPML folder to category and detect country."""
    category = FOLDER_TO_CATEGORY.get(folder, "blog")
    country = detect_country(url, title)
    return category, country


def escape_sql_string(s: str) -> str:
    """Escape a string for SQL insertion."""
    return s.replace("\\", "\\\\").replace("'", "\\'")


# =============================================================================
# Existing feed URL extraction from init.sql
# =============================================================================
def load_existing_urls_from_sql() -> set[str]:
    """Extract existing feed_urls from init.sql (as dedup fallback when DB is unavailable)."""
    sql_path = PROJECT_ROOT / "sql" / "init.sql"
    if not sql_path.exists():
        logger.warning(f"init.sql not found at {sql_path}")
        return set()

    existing: set[str] = set()
    with open(sql_path, encoding="utf-8") as f:
        content = f.read()

    # Find all single-quoted URL strings in INSERT INTO rss_feeds blocks
    # Rows look like: ('title', 'feed_url', 'site_url', ...
    for m in re.finditer(
        r"^\s*\('([^']*)',\s*'([^']*)',", content, re.MULTILINE
    ):
        feed_url = m.group(2)
        if feed_url and (feed_url.startswith("http") or feed_url.startswith("/")):
            existing.add(feed_url)

    logger.info(f"Loaded {len(existing)} existing feed URLs from init.sql")
    return existing


async def load_existing_urls_from_db() -> set[str]:
    """Query DB for existing feed_urls."""
    try:
        from core.database import get_session_factory
        from sqlalchemy import text

        session_factory = get_session_factory()
        async with session_factory() as session:
            result = await session.execute(text("SELECT feed_url FROM rss_feeds"))
            urls = {row[0] for row in result.fetchall()}
            logger.info(f"Loaded {len(urls)} existing feed URLs from database")
            return urls
    except Exception as e:
        logger.warning(f"Cannot connect to DB ({e}), falling back to init.sql")
        return set()


# =============================================================================
# Feed validation
# =============================================================================
class FeedCheckResult(NamedTuple):
    url: str
    valid: bool
    final_url: str  # after redirects
    content_type: str
    status_code: int
    error: str


async def check_feed(
    client: httpx.AsyncClient, url: str, semaphore: asyncio.Semaphore
) -> FeedCheckResult:
    """Check if a single URL is a valid RSS/Atom feed."""
    async with semaphore:
        try:
            resp = await client.get(url, follow_redirects=True, timeout=8.0)
            ct = resp.headers.get("content-type", "").lower()
            body_prefix = resp.text[:2000] if resp.status_code == 200 else ""

            # Validity criteria
            ct_ok = any(kw in ct for kw in ("xml", "rss", "atom", "feed"))
            body_ok = any(
                tag in body_prefix
                for tag in ("<rss", "<feed", "<channel", "<?xml")
            )
            valid = resp.status_code == 200 and (ct_ok or body_ok)

            return FeedCheckResult(
                url=url,
                valid=valid,
                final_url=str(resp.url),
                content_type=ct,
                status_code=resp.status_code,
                error="",
            )
        except httpx.TimeoutException:
            return FeedCheckResult(url, False, url, "", 0, "timeout")
        except httpx.TooManyRedirects:
            return FeedCheckResult(url, False, url, "", 0, "too_many_redirects")
        except Exception as e:
            return FeedCheckResult(url, False, url, "", 0, str(e)[:80])


async def validate_feeds_batch(
    urls: list[str], concurrency: int = 20
) -> dict[str, FeedCheckResult]:
    """Validate a list of feed URLs concurrently."""
    semaphore = asyncio.Semaphore(concurrency)
    results: dict[str, FeedCheckResult] = {}

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; ResearchPulse-FeedValidator/1.0; "
            "+https://github.com/ResearchPulse)"
        )
    }

    async with httpx.AsyncClient(
        headers=headers,
        follow_redirects=True,
        timeout=httpx.Timeout(8.0),
        limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
    ) as client:
        tasks = [check_feed(client, url, semaphore) for url in urls]
        total = len(tasks)
        done = 0

        for coro in asyncio.as_completed(tasks):
            result = await coro
            results[result.url] = result
            done += 1
            if done % 50 == 0 or done == total:
                valid_so_far = sum(1 for r in results.values() if r.valid)
                logger.info(
                    f"Progress: {done}/{total} checked, "
                    f"{valid_so_far} valid so far"
                )

    return results


# =============================================================================
# SQL generation
# =============================================================================
def build_insert_sql(
    feeds: list[tuple[str, str, str, str]],
    check_results: dict[str, FeedCheckResult],
    existing_urls: set[str],
    today: str,
) -> tuple[str, list[dict]]:
    """Build INSERT IGNORE SQL for valid new feeds.

    Returns:
        (sql_block: str, new_feeds: list[dict])
    """
    # Deduplicate by URL within the OPML itself
    seen_urls: set[str] = set()
    valid_new: list[dict] = []

    for folder, title, xml_url, html_url in feeds:
        result = check_results.get(xml_url)
        if result is None or not result.valid:
            continue

        # Use final URL (after redirect) for dedup & storage
        final_url = result.final_url if result.final_url else xml_url

        if final_url in existing_urls or xml_url in existing_urls:
            continue
        if final_url in seen_urls:
            continue
        seen_urls.add(final_url)

        category, country = get_category_country(folder, xml_url, title)
        site_url = html_url or ""

        valid_new.append(
            {
                "title": title,
                "feed_url": final_url,
                "site_url": site_url,
                "category": category,
                "country": country,
                "folder": folder,
            }
        )

    if not valid_new:
        return "", []

    lines = [
        "-- " + "=" * 60,
        f"-- OPML Import: user-provided feed collection ({today})",
        "-- is_active=0 by default; enable selectively",
        "-- " + "=" * 60,
        "INSERT IGNORE INTO `rss_feeds` (`title`, `feed_url`, `site_url`, `category`, `description`, `is_active`, `country`, `news_category`) VALUES",
    ]

    rows = []
    for feed in valid_new:
        country_val = f"'{feed['country']}'" if feed["country"] else "NULL"
        rows.append(
            f"  ('{escape_sql_string(feed['title'])}', "
            f"'{escape_sql_string(feed['feed_url'])}', "
            f"'{escape_sql_string(feed['site_url'])}', "
            f"'{escape_sql_string(feed['category'])}', "
            f"'', 0, {country_val}, NULL)"
        )

    lines.append(",\n".join(rows) + ";")
    return "\n".join(lines), valid_new


# =============================================================================
# Main
# =============================================================================
async def main(dry_run: bool = False, no_db: bool = False) -> None:
    logger.info("=" * 60)
    logger.info("ResearchPulse — OPML Feed Validator")
    logger.info("=" * 60)

    # 1. Build dedup set
    if no_db:
        existing_urls = load_existing_urls_from_sql()
    else:
        existing_urls = await load_existing_urls_from_db()
        if not existing_urls:
            existing_urls = load_existing_urls_from_sql()

    # 2. Classify each OPML feed
    all_urls = list({feed[2] for feed in OPML_FEEDS})  # unique xmlUrls
    already_exists = {
        url for url in all_urls if url in existing_urls
    }
    to_check = [url for url in all_urls if url not in already_exists]

    logger.info(
        f"\nOPML feeds: {len(OPML_FEEDS)} entries, "
        f"{len(all_urls)} unique URLs"
    )
    logger.info(f"Already in DB/init.sql: {len(already_exists)}")
    logger.info(f"URLs to validate: {len(to_check)}")

    # 3. Validate
    logger.info("\nValidating feeds (concurrency=20, timeout=8s)...")
    check_results = await validate_feeds_batch(to_check, concurrency=20)

    valid_count = sum(1 for r in check_results.values() if r.valid)
    invalid_count = sum(1 for r in check_results.values() if not r.valid)

    # 4. Print invalid summary
    logger.info("\n--- Invalid / Dead feeds ---")
    for url, result in sorted(check_results.items()):
        if not result.valid:
            logger.info(
                f"  DEAD [{result.status_code}] {result.error or result.content_type} | {url}"
            )

    # 5. Build SQL
    today = date.today().isoformat()
    sql_block, new_feeds = build_insert_sql(OPML_FEEDS, check_results, existing_urls, today)

    # 6. Print summary
    logger.info("\n" + "=" * 60)
    logger.info("Summary:")
    logger.info(f"  Total unique OPML URLs:  {len(all_urls)}")
    logger.info(f"  Already in DB:           {len(already_exists)}")
    logger.info(f"  Checked:                 {len(to_check)}")
    logger.info(f"  Valid (reachable):       {valid_count}")
    logger.info(f"  Invalid/dead:            {invalid_count}")
    logger.info(f"  New valid (not in DB):   {len(new_feeds)}")
    logger.info("=" * 60)

    if not new_feeds:
        logger.info("No new valid feeds to add.")
        return

    # 7. Write to valid_new_feeds.sql
    output_path = PROJECT_ROOT / "valid_new_feeds.sql"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(sql_block + "\n")
    logger.info(f"\nSQL written to: {output_path}")

    # 8. Optionally append to init.sql
    if not dry_run:
        init_sql_path = PROJECT_ROOT / "sql" / "init.sql"
        with open(init_sql_path, "a", encoding="utf-8") as f:
            f.write("\n\n" + sql_block + "\n")
        logger.info(f"Appended to: {init_sql_path}")
    else:
        logger.info("Dry-run mode: init.sql NOT modified")

    # 9. Print category breakdown
    from collections import Counter
    cats = Counter(f["category"] for f in new_feeds)
    logger.info("\nNew feeds by category:")
    for cat, cnt in sorted(cats.items(), key=lambda x: -x[1]):
        logger.info(f"  {cat}: {cnt}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Validate OPML feeds and generate SQL for valid new entries"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not modify init.sql, only write valid_new_feeds.sql",
    )
    parser.add_argument(
        "--no-db",
        action="store_true",
        help="Skip DB connection, use init.sql for dedup instead",
    )
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run, no_db=args.no_db))
