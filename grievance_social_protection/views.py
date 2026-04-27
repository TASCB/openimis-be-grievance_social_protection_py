import os
import uuid
import logging

import core
from django.conf import settings
from django.http import HttpResponse
from django.utils.translation import gettext as _
from rest_framework import status as drf_status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from core.views import check_user_rights

from .apps import TicketConfig
from .models import Ticket, TicketAttachment, TicketMutation

logger = logging.getLogger(__name__)

ALLOWED_MIME_TYPES = {
    # images
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    # video
    "video/mp4",
    "video/webm",
    # audio
    "audio/mpeg",
    "audio/wav",
    "audio/ogg",
    # documents
    "application/pdf",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB
MAX_FILES_PER_TICKET = 5


def _attachments_root():
    root = TicketConfig.tickets_attachments_root_path
    if root:
        return root

    media_root = getattr(settings, "MEDIA_ROOT", None)
    if media_root:
        return os.path.join(media_root, "grievance_attachments")

    return None


@api_view(["GET"])
@permission_classes([check_user_rights(TicketConfig.gql_query_tickets_perms)])
def attach(request):
    """Download a single ticket attachment by id."""
    attachment = (
        TicketAttachment.objects.filter(*core.filter_validity())
        .filter(id=request.GET.get("id"))
        .first()
    )
    if not attachment:
        return Response({"error": "not found"}, status=drf_status.HTTP_404_NOT_FOUND)

    root = _attachments_root()
    if not root or not attachment.url:
        return Response({"error": "not found"}, status=drf_status.HTTP_404_NOT_FOUND)

    full_path = os.path.join(root, attachment.url)
    if not os.path.isfile(full_path):
        return Response({"error": "not found"}, status=drf_status.HTTP_404_NOT_FOUND)

    content_type = attachment.mime_type or "application/octet-stream"
    response = HttpResponse(content_type=content_type)
    response["Content-Disposition"] = (
        f'attachment; filename="{attachment.filename}"'
    )
    with open(full_path, "rb") as f:
        response.write(f.read())
    return response


def _safe_filename(original):
    base = os.path.basename(original or "").replace("\\", "_").replace("/", "_")
    return base or "file"


@api_view(["POST"])
@permission_classes([check_user_rights(TicketConfig.gql_mutation_create_tickets_perms)])
def upload(request):
    """Multipart upload endpoint. Accepts ticket_uuid or client_mutation_id and 'files'."""
    ticket_uuid = request.data.get("ticket_uuid")
    client_mutation_id = request.data.get("client_mutation_id")

    ticket = None
    if ticket_uuid:
        ticket = Ticket.objects.filter(id=ticket_uuid, is_deleted=False).first()
    elif client_mutation_id:
        tm = (
            TicketMutation.objects.select_related("ticket", "mutation")
            .filter(mutation__client_mutation_id=client_mutation_id)
            .first()
        )
        ticket = tm.ticket if tm and not tm.ticket.is_deleted else None
    else:
        return Response(
            {"error": "ticket_uuid or client_mutation_id is required"},
            status=drf_status.HTTP_400_BAD_REQUEST,
        )
    if not ticket:
        return Response(
            {"error": "ticket not found"}, status=drf_status.HTTP_404_NOT_FOUND
        )

    root = _attachments_root()
    if not root:
        return Response(
            {"error": "attachment storage is not configured"},
            status=drf_status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    os.makedirs(root, exist_ok=True)

    files = request.FILES.getlist("files")
    if not files:
        return Response(
            {"error": "no files provided"}, status=drf_status.HTTP_400_BAD_REQUEST
        )

    existing_count = TicketAttachment.objects.filter(
        ticket=ticket, *core.filter_validity()
    ).count()
    if existing_count + len(files) > MAX_FILES_PER_TICKET:
        return Response(
            {
                "error": (
                    f"attachment limit exceeded: ticket has {existing_count}, "
                    f"uploading {len(files)}, max {MAX_FILES_PER_TICKET}"
                )
            },
            status=drf_status.HTTP_400_BAD_REQUEST,
        )

    saved = []
    errors = []
    for f in files:
        if f.size > MAX_FILE_SIZE:
            errors.append({"filename": f.name, "error": "file exceeds 25MB limit"})
            continue
        mime = (f.content_type or "").lower()
        if mime not in ALLOWED_MIME_TYPES:
            errors.append({"filename": f.name, "error": f"mime type {mime} not allowed"})
            continue

        safe = _safe_filename(f.name)
        stored_name = f"{uuid.uuid4()}_{safe}"
        dest = os.path.join(root, stored_name)
        try:
            with open(dest, "wb") as out:
                for chunk in f.chunks():
                    out.write(chunk)
        except Exception as exc:
            logger.exception("Failed writing attachment")
            errors.append({"filename": f.name, "error": str(exc)})
            continue

        attachment = TicketAttachment.objects.create(
            ticket=ticket,
            filename=safe,
            mime_type=mime,
            url=stored_name,
        )
        saved.append(
            {
                "id": str(attachment.id),
                "filename": attachment.filename,
                "mime_type": attachment.mime_type,
            }
        )

    http_status = (
        drf_status.HTTP_200_OK if saved else drf_status.HTTP_400_BAD_REQUEST
    )
    return Response({"saved": saved, "errors": errors}, status=http_status)
