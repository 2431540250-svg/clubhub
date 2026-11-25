// Xác nhận trước khi submit các form nguy hiểm (xóa...)
document.addEventListener("submit", (e) => {
  const msg = e.target.dataset.confirm;
  if (msg && !confirm(msg)) e.preventDefault();
});

// Thông báo thành công/thông tin tự ẩn sau 5 giây.
// Thông báo LỖI và CẢNH BÁO giữ nguyên cho tới khi người dùng bấm ✕.
setTimeout(() => {
  document.querySelectorAll(".flash-wrap .alert-success, .flash-wrap .alert-info").forEach((el) => {
    bootstrap.Alert.getOrCreateInstance(el).close();
  });
}, 5000);

// Tô đỏ ô nhập sai ngay trên trình duyệt (ô bắt buộc bị bỏ trống, email sai...)
document.addEventListener("invalid", (e) => {
  const el = e.target;
  el.classList.add("is-invalid");
  if (!el.nextElementSibling || !el.nextElementSibling.classList.contains("invalid-feedback")) {
    const fb = document.createElement("div");
    fb.className = "invalid-feedback d-block js-feedback";
    fb.textContent = el.validationMessage;
    el.insertAdjacentElement("afterend", fb);
  }
}, true);

// Khi người dùng sửa ô bị tô đỏ -> bỏ tô đỏ
document.addEventListener("input", (e) => {
  const el = e.target;
  if (!el.classList || !el.classList.contains("is-invalid")) return;
  el.classList.remove("is-invalid");
  const fb = el.nextElementSibling;
  if (fb && fb.classList.contains("invalid-feedback")) fb.remove();
});

// Cuộn tới ô lỗi đầu tiên do server trả về
window.addEventListener("load", () => {
  const first = document.querySelector("form .is-invalid");
  if (first) { first.scrollIntoView({ block: "center" }); first.focus({ preventScroll: true }); }
});

// Bảng trên điện thoại: gắn nhãn cột cho từng ô (dùng với class .table-stack)
document.querySelectorAll("table.table-stack").forEach((t) => {
  const heads = [...t.querySelectorAll("thead th")].map((th) => th.textContent.trim());
  t.querySelectorAll("tbody tr").forEach((tr) => {
    [...tr.children].forEach((td, i) => { if (heads[i]) td.dataset.label = heads[i]; });
  });
});
