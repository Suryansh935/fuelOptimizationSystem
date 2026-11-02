from django.urls import path

from optimizer.views import route_plan


urlpatterns = [
    path("route/plan/", route_plan, name="route-plan"),
]
