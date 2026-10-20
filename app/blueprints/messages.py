"""Direct messaging between members — how a recruiter reaches a candidate."""
from flask import Blueprint, abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_

from app.extensions import db
from app.forms import MessageForm
from app.models import Message, User
from app.utils import approved_required

messages_bp = Blueprint("messages", __name__)


@messages_bp.route("/")
@login_required
def inbox():
    received = (
        Message.query.filter_by(recipient_id=current_user.id)
        .order_by(Message.created_at.desc())
        .all()
    )
    sent = (
        Message.query.filter_by(sender_id=current_user.id)
        .order_by(Message.created_at.desc())
        .all()
    )
    return render_template("messages/inbox.html", received=received, sent=sent)


@messages_bp.route("/<int:message_id>")
@login_required
def view(message_id):
    message = db.session.get(Message, message_id)
    if message is None:
        abort(404)
    if current_user.id not in (message.sender_id, message.recipient_id):
        abort(403)

    if message.recipient_id == current_user.id and not message.is_read:
        message.is_read = True
        db.session.commit()

    other_id = message.sender_id if message.recipient_id == current_user.id else message.recipient_id
    thread = (
        Message.query.filter(
            or_(
                db.and_(Message.sender_id == current_user.id, Message.recipient_id == other_id),
                db.and_(Message.sender_id == other_id, Message.recipient_id == current_user.id),
            )
        )
        .order_by(Message.created_at)
        .all()
    )
    return render_template(
        "messages/view.html", message=message, thread=thread,
        other=db.session.get(User, other_id),
    )


@messages_bp.route("/to/<int:user_id>", methods=["GET", "POST"])
@login_required
@approved_required
def compose(user_id):
    recipient = db.session.get(User, user_id)
    if recipient is None or recipient.id == current_user.id:
        abort(404)
    if not recipient.can_participate:
        abort(404)

    form = MessageForm()
    if form.validate_on_submit():
        db.session.add(Message(
            sender_id=current_user.id, recipient_id=recipient.id,
            subject=(form.subject.data or "").strip() or "(no subject)",
            body=form.body.data,
        ))
        db.session.commit()
        flash(f"Message sent to {recipient.full_name}.", "success")
        return redirect(url_for("messages.inbox"))

    return render_template("messages/compose.html", form=form, recipient=recipient)


@messages_bp.route("/<int:message_id>/delete", methods=["POST"])
@login_required
def delete(message_id):
    message = db.session.get(Message, message_id)
    if message is None:
        abort(404)
    if current_user.id not in (message.sender_id, message.recipient_id):
        abort(403)
    db.session.delete(message)
    db.session.commit()
    flash("Message deleted.", "info")
    return redirect(url_for("messages.inbox"))
