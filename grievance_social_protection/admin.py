from django.contrib import admin
from .models import GrievanceType, GrievanceCategory


@admin.register(GrievanceType)
class GrievanceTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active")
    search_fields = ("name",)


@admin.register(GrievanceCategory)
class GrievanceCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "type", "code", "is_active")
    list_filter = ("type",)
    search_fields = ("name",)
