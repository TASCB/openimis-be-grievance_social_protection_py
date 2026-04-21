import os
import json
import uuid
import logging

import core
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, JsonResponse, HttpResponseNotAllowed
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_exempt

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


def attach(request):
    """Download a single ticket attachment by id."""
    queryset = TicketAttachment.objects.filter(*core.filter_validity())
    attachment = queryset.filter(id=request.GET.get("id")).first()
    if not attachment:
        raise PermissionDenied(_("unauthorized"))

    if not request.user.is_authenticated:
        raise PermissionDenied(_("unauthorized"))

    root = TicketConfig.tickets_attachments_root_path
    if not root or not attachment.url:
        return HttpResponse(status=404)

    full_path = os.path.join(root, attachment.url)
    if not os.path.isfile(full_path):
        return HttpResponse(status=404)

    content_type = attachment.mime_type or "application/octet-stream"
    response = HttpResponse(content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{attachment.filename}"'
    with open(full_path, "rb") as f:
        response.write(f.read())
    return response


def _safe_filename(original):
    base = os.path.basename(original or "").replace("\\", "_").replace("/", "_")
    return base or "file"


@csrf_exempt
def upload(request):
    """Multipart upload endpoint. Accepts field ticket_uuid and one or many 'files'."""
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    if not request.user.is_authenticated:
        raise PermissionDenied(_("unauthorized"))
    if not request.user.has_perms(TicketConfig.gql_mutation_create_tickets_perms):
        raise PermissionDenied(_("unauthorized"))

    ticket_uuid = request.POST.get("ticket_uuid")
    client_mutation_id = request.POST.get("client_mutation_id")
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
        return JsonResponse(
            {"error": "ticket_uuid or client_mutation_id is required"}, status=400
        )
    if not ticket:
        return JsonResponse({"error": "ticket not found"}, status=404)

    root = TicketConfig.tickets_attachments_root_path
    if not root:
        return JsonResponse(
            {"error": "tickets_attachments_root_path is not configured"}, status=500
        )
    os.makedirs(root, exist_ok=True)

    files = request.FILES.getlist("files")
    if not files:
        return JsonResponse({"error": "no files provided"}, status=400)

    existing_count = TicketAttachment.objects.filter(
        ticket=ticket, *core.filter_validity()
    ).count()
    if existing_count + len(files) > MAX_FILES_PER_TICKET:
        return JsonResponse(
            {
                "error": (
                    f"attachment limit exceeded: ticket has {existing_count}, "
                    f"uploading {len(files)}, max {MAX_FILES_PER_TICKET}"
                )
            },
            status=400,
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

    status = 200 if saved else 400
    return JsonResponse({"saved": saved, "errors": errors}, status=status)
