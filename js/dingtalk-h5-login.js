/**
 * 钉钉客户端内 H5：requestAuthCode -> POST /api/dingtalk/h5-auth
 * 需在 .env 开启 DINGTALK_USE_H5_JSAPI=1 并配置 DINGTALK_CORP_ID
 *
 * 行为说明：
 * - 仅支持钉钉工作台内（内置浏览器）登录。
 * - 不再提供浏览器扫码/OAuth 入口。
 */
(function () {
  var UA = navigator.userAgent || "";
  var inDingTalk = /DingTalk|AliApp\(DingTalk/i.test(UA);
  var AUTO_LOGIN_KEY = "keapprove_dt_h5_autologin_tried";

  function show(el, on) {
    if (!el) return;
    el.style.display = on ? "" : "none";
  }

  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      var s = document.createElement("script");
      s.src = src;
      s.async = true;
      s.onload = function () {
        resolve();
      };
      s.onerror = function () {
        reject(new Error("load fail"));
      };
      document.head.appendChild(s);
    });
  }

  /**
   * @param {string} corpId
   * @param {HTMLButtonElement} h5Btn
   * @returns {Promise<boolean>} 是否完成换票并成功（会 reload，正常不会走到 false）
   */
  async function runH5Login(corpId, h5Btn) {
    if (!corpId) return false;
    if (h5Btn) h5Btn.disabled = true;
    try {
      if (!window.dd) {
        await loadScript("https://g.alicdn.com/dingding/dingtalk-jsapi/2.13.42/dingtalk.open.js");
      }
      if (!window.dd || !dd.runtime || !dd.runtime.permission || !dd.runtime.permission.requestAuthCode) {
        alert("当前环境不支持钉钉 JSAPI，请从钉钉客户端打开微应用首页。");
        return false;
      }
      return await new Promise(function (resolve) {
        dd.runtime.permission.requestAuthCode({
          corpId: corpId,
          onSuccess: async function (info) {
            var code = info && (info.code || info.authCode);
            if (!code) {
              alert("未获取到授权码");
              resolve(false);
              return;
            }
            try {
              var resp = await fetch("/api/dingtalk/h5-auth", {
                method: "POST",
                headers: { "content-type": "application/json" },
                body: JSON.stringify({ authCode: code }),
              });
              var d = await resp.json().catch(function () {
                return {};
              });
              if (resp.ok && d.ok) {
                window.location.reload();
                resolve(true);
              } else {
                alert((d && d.msg) || "登录失败");
                resolve(false);
              }
            } catch (e2) {
              alert("请求失败：" + (e2.message || e2));
              resolve(false);
            }
          },
          onFail: function (err) {
            alert(
              err && (err.errorMessage || err.message)
                ? err.errorMessage || err.message
                : "钉钉授权失败"
            );
            resolve(false);
          },
        });
      });
    } catch (e) {
      alert("加载或调用钉钉接口失败：" + (e.message || e));
      return false;
    } finally {
      if (h5Btn) h5Btn.disabled = false;
    }
  }

  async function init() {
    var h5Btn = document.getElementById("h5LoginBtn");
    var hint = document.getElementById("dingtalkEnvHint");

    var cfg = {};
    try {
      var r = await fetch("/api/dingtalk/web-config");
      cfg = await r.json();
    } catch (e) {
      return;
    }

    var me = {};
    try {
      var mr = await fetch("/api/me");
      me = await mr.json().catch(function () {
        return {};
      });
    } catch (e2) {
      me = {};
    }
    var loggedIn = !!(me && me.logged_in);

    var h5Ok = !!(cfg && cfg.h5_jsapi_enabled && cfg.corp_id);

    // 仅支持钉钉工作台内登录
    if (!inDingTalk) {
      show(h5Btn, false);
      if (hint) {
        hint.textContent = "请从钉钉工作台打开本应用。当前页面不支持浏览器扫码登录。";
        hint.className = "small text-danger text-end";
      }
      return;
    }

    // 钉钉内置浏览器：不应默认引导扫码 OAuth
    if (h5Ok) {
      if (hint) {
        hint.textContent = loggedIn
          ? "已通过钉钉登录。"
          : "从钉钉工作台打开：正在自动免登（无需扫码）。若失败请刷新页面重试。";
      }
      // 只做自动免登，不向用户展示任何登录按钮
      show(h5Btn, false);

      // 未登录时每个标签页尝试自动免登一次
      if (!loggedIn && !sessionStorage.getItem(AUTO_LOGIN_KEY)) {
        sessionStorage.setItem(AUTO_LOGIN_KEY, "1");
        setTimeout(function () {
          runH5Login(cfg.corp_id, h5Btn);
        }, 500);
      }
      return;
    }

    // 钉钉内但未开启 H5 配置
    show(h5Btn, false);
    if (hint) {
      hint.innerHTML =
        "检测到<strong>钉钉内打开</strong>，但服务端未开启工作台免登。请在服务器 <code>.env</code> 设置 " +
        "<code>DINGTALK_USE_H5_JSAPI=1</code> 并填写企业 <code>DINGTALK_CORP_ID</code>（与 H5 微应用同一套 ClientId/Secret 即可），重启服务后刷新。详见项目内 <strong>DINGTALK-H5.md</strong>。";
      hint.className = "small text-danger text-end";
      hint.style.maxWidth = "520px";
    }
  }

  // 供页面在 401 时主动拉起钉钉内登录
  window.keDingTalkH5Login = function () {
    var h5Btn = document.getElementById("h5LoginBtn");
    fetch("/api/dingtalk/web-config")
      .then(function (r) { return r.json(); })
      .then(function (cfg) {
        if (!cfg || !cfg.h5_jsapi_enabled || !cfg.corp_id) {
          alert("未启用钉钉工作台免登，请联系管理员配置 DINGTALK_USE_H5_JSAPI=1 与 DINGTALK_CORP_ID。");
          return false;
        }
        return runH5Login(cfg.corp_id, h5Btn);
      })
      .catch(function () {
        alert("读取钉钉配置失败，请稍后重试。");
      });
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
