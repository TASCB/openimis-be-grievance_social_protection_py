from django.contrib import admin
from .models import GrievanceType, GrievanceCategory, GrievanceChannel


class HistoryBusinessModelAdmin(admin.ModelAdmin):
    readonly_fields = (
        "user_created",
        "date_created",
        "user_updated",
        "date_updated",
        "version",
    )
    exclude = ("date_valid_from", "date_valid_to", "json_ext", "replacement_uuid")

    def save_model(self, request, obj, form, change):
        if not change:
            obj.user_created = request.user
        obj.user_updated = request.user
        obj.save(user=request.user)

    def delete_model(self, request, obj):
        obj.delete(user=request.user)

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            obj.delete(user=request.user)


@admin.register(GrievanceCategory)
class GrievanceCategoryAdmin(HistoryBusinessModelAdmin):
    list_display = ("name", "code", "timeline", "is_active")
    search_fields = ("name",)


@admin.register(GrievanceType)
class GrievanceTypeAdmin(HistoryBusinessModelAdmin):
    list_display = ("name", "category", "code", "is_active")
    list_filter = ("category",)
    search_fields = ("name",)


@admin.register(GrievanceChannel)
class GrievanceChannelAdmin(HistoryBusinessModelAdmin):
    list_display = ("name", "code", "is_active")
    search_fields = ("name",)
