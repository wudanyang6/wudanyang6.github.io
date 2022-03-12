$(".post .post-content img").each(function () {
    $(this).attr('src', "/img/" + $(this).attr('src'))
})