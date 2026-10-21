"""Albums of photographs, uploaded by an administrator."""
import io

from tests.conftest import as_admin, login


def _png(size=(40, 30), colour=(32, 44, 84)):
    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", size, colour).save(buffer, "PNG")
    buffer.seek(0)
    return buffer


def _album(client, title="Alumni Meet 2026", **overrides):
    data = {"title": title, "description": "A day by the Chaliyar.",
            "event_date": "2026-12-20", "is_published": "y", "sort_order": "10"}
    data.update(overrides)
    return client.post("/admin/gallery/new", data=data, follow_redirects=True)


def test_public_gallery_is_empty_at_first(client, app):
    response = client.get("/gallery")
    assert response.status_code == 200
    assert "No albums published yet" in response.get_data(as_text=True)


def test_album_lifecycle_with_uploads(client, app):
    from app.models import GalleryAlbum, GalleryImage
    as_admin(client)
    response = _album(client)
    assert "saved" in response.get_data(as_text=True)

    with app.app_context():
        album = GalleryAlbum.query.first()
        assert album.slug == "alumni-meet-2026"
        assert album.image_count == 0
        album_id = album.id

    response = client.post(f"/admin/gallery/{album_id}/images", follow_redirects=True,
                           content_type="multipart/form-data", data={
        "images": [(_png(), "one.png"), (_png(colour=(121, 186, 76)), "two.png")],
        "caption": "Lunch under the trees",
    })
    assert "2 images added" in response.get_data(as_text=True)

    with app.app_context():
        album = GalleryAlbum.query.first()
        assert album.image_count == 2
        assert album.cover is not None, "the first image stands in as the cover"
        for image in album.images:
            assert (app.config["GALLERY_FOLDER"] / image.filename).exists()
            assert image.caption == "Lunch under the trees"

    client.post("/auth/logout")
    body = client.get("/gallery").get_data(as_text=True)
    assert "Alumni Meet 2026" in body and "2 photos" in body
    body = client.get("/gallery/alumni-meet-2026").get_data(as_text=True)
    assert body.count("uploads/gallery/") >= 2
    assert "Lunch under the trees" in body


def test_captions_cover_and_deletion(client, app):
    from app.extensions import db
    from app.models import GalleryAlbum, GalleryImage
    as_admin(client)
    _album(client)
    with app.app_context():
        album_id = GalleryAlbum.query.first().id
    client.post(f"/admin/gallery/{album_id}/images", content_type="multipart/form-data",
                data={"images": [(_png(), "one.png"), (_png(), "two.png")]})

    with app.app_context():
        first, second = GalleryImage.query.order_by(GalleryImage.id).all()
        first_id, second_id = first.id, second.id
        stored = second.filename

    client.post(f"/admin/gallery/image/{first_id}/update", follow_redirects=True,
                data={"caption": "The 1998 batch", "sort_order": "5"})
    with app.app_context():
        from app.models import GalleryImage as GI
        image = db.session.get(GI, first_id)
        assert image.caption == "The 1998 batch" and image.sort_order == 5

    client.post(f"/admin/gallery/image/{second_id}/cover", follow_redirects=True)
    with app.app_context():
        assert db.session.get(GalleryAlbum, album_id).cover_image_id == second_id

    response = client.post(f"/admin/gallery/image/{second_id}/delete", follow_redirects=True)
    assert "Image removed" in response.get_data(as_text=True)
    with app.app_context():
        album = db.session.get(GalleryAlbum, album_id)
        assert album.image_count == 1
        assert album.cover_image_id is None, "the cover is cleared when that image goes"
        assert not (app.config["GALLERY_FOLDER"] / stored).exists(), "the file is deleted too"


def test_deleting_an_album_removes_its_files(client, app):
    from app.models import GalleryAlbum, GalleryImage
    as_admin(client)
    _album(client)
    with app.app_context():
        album_id = GalleryAlbum.query.first().id
    client.post(f"/admin/gallery/{album_id}/images", content_type="multipart/form-data",
                data={"images": [(_png(), "one.png")]})
    with app.app_context():
        stored = GalleryImage.query.first().filename

    response = client.post(f"/admin/gallery/{album_id}/delete", follow_redirects=True)
    assert "were removed" in response.get_data(as_text=True)
    with app.app_context():
        assert GalleryAlbum.query.count() == 0
        assert GalleryImage.query.count() == 0, "the cascade removes the image rows"
        assert not (app.config["GALLERY_FOLDER"] / stored).exists()


def test_an_unpublished_album_is_hidden_from_visitors(client, app):
    as_admin(client)
    _album(client, title="Draft album", is_published="")
    client.post("/auth/logout")
    assert "Draft album" not in client.get("/gallery").get_data(as_text=True)
    assert client.get("/gallery/draft-album").status_code == 404
    # but an administrator can preview it
    as_admin(client)
    assert client.get("/gallery/draft-album").status_code == 200


def test_a_file_that_is_not_an_image_is_refused(client, app):
    from app.models import GalleryAlbum, GalleryImage
    as_admin(client)
    _album(client)
    with app.app_context():
        album_id = GalleryAlbum.query.first().id

    response = client.post(f"/admin/gallery/{album_id}/images", follow_redirects=True,
                           content_type="multipart/form-data", data={
        "images": [(io.BytesIO(b"<html>not an image</html>"), "evil.png")],
    })
    assert "not a readable image" in response.get_data(as_text=True)
    with app.app_context():
        assert GalleryImage.query.count() == 0

    response = client.post(f"/admin/gallery/{album_id}/images", follow_redirects=True,
                           content_type="multipart/form-data", data={
        "images": [(io.BytesIO(b"MZ"), "payload.exe")],
    })
    assert "Images only" in response.get_data(as_text=True)


def test_large_photographs_are_resized(client, app):
    from PIL import Image
    from app.models import GalleryAlbum, GalleryImage
    as_admin(client)
    _album(client)
    with app.app_context():
        album_id = GalleryAlbum.query.first().id
    client.post(f"/admin/gallery/{album_id}/images", content_type="multipart/form-data",
                data={"images": [(_png(size=(3000, 2000)), "huge.png")]})
    with app.app_context():
        image = GalleryImage.query.first()
        with Image.open(app.config["GALLERY_FOLDER"] / image.filename) as opened:
            assert max(opened.size) <= 1600


def test_duplicate_titles_get_distinct_slugs(client, app):
    from app.models import GalleryAlbum
    as_admin(client)
    _album(client, title="Farewell")
    _album(client, title="Farewell")
    with app.app_context():
        slugs = [a.slug for a in GalleryAlbum.query.all()]
        assert len(slugs) == 2 and len(set(slugs)) == 2


def test_members_cannot_manage_the_gallery(client, app):
    login(client, "seeker@test.edu")
    assert client.get("/admin/gallery").status_code == 403
    assert client.post("/admin/gallery/new", data={"title": "Sneaky"}).status_code == 403


def test_captions_are_escaped(client, app):
    from app.models import GalleryAlbum
    as_admin(client)
    _album(client, title="Escaping test", description='<script>alert("x")</script>')
    with app.app_context():
        album_id = GalleryAlbum.query.first().id
    client.post(f"/admin/gallery/{album_id}/images", content_type="multipart/form-data",
                data={"images": [(_png(), "one.png")], "caption": '<img src=x onerror=alert(1)>'})
    client.post("/auth/logout")
    body = client.get("/gallery/escaping-test").get_data(as_text=True)
    assert "<script>alert" not in body
    assert "<img src=x onerror" not in body
    assert "&lt;script&gt;" in body
