# coding=utf-8

from django.db import models
from django.contrib.gis.db import models
from django.contrib.contenttypes import generic
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import User

from stdimage import StdImageField
from autoslug import AutoSlugField
from jsonfield.fields import JSONField


class AdPicture(models.Model):
    """
    Ad picture model

    """
    content_type = models.ForeignKey(ContentType)
    object_id = models.PositiveIntegerField()
    content_object = generic.GenericForeignKey('content_type', 'object_id')
    image = StdImageField(upload_to="pictures/", size=(640, 500), 
                          thumbnail_size=(100, 100))
    title = models.CharField('Description de la photo', max_length = 255, 
                             null = True, blank = True)


class AdContact(models.Model):
    """
    Ad contact model

    """
    user = models.ForeignKey(User)
    content_type = models.ForeignKey(ContentType)
    object_pk = models.PositiveIntegerField()
    content_object = generic.GenericForeignKey(ct_field="content_type",
                                               fk_field="object_pk")
    message = models.TextField('Votre message')


class AdSearch(models.Model):
    """
    AdSearch base

    Application using this need to have a proxy model 
    to define unicode string repr of each AdSearch depending on ad fields.
    """
    search = models.CharField(max_length=2550)
    user = models.ForeignKey(User)
    create_date = models.DateTimeField(auto_now_add = True)  
    content_type = models.ForeignKey(ContentType)


class Ad(models.Model):
    """
    Ad abstract base model

    """
    user = models.ForeignKey(User)
    slug = AutoSlugField(populate_from='get_full_description', 
                         always_update=True, unique=True)
    description = models.TextField("", null=True, blank=True)
    user_entered_address = models.CharField("Adresse", max_length=2550, 
            help_text="Adresse complète, ex. : <i>5 rue de Verneuil Paris</i>")
    address = JSONField(null=True, blank=True)
    location = models.PointField(srid=900913)
    pictures = generic.GenericRelation(AdPicture)
    update_date = models.DateTimeField(auto_now = True)
    create_date = models.DateTimeField(auto_now_add = True) 
    delete_date = models.DateTimeField(null = True, blank = True)
    visible = models.BooleanField()

    objects = models.GeoManager()
    
    def get_full_description(self, instance=None):
        """return a resume description for slug"""
        return self.slug

    class Meta:
        abstract = True
    
    def __unicode__(self):
        return self.slug


# South definition for custom fields
from south.modelsinspector import add_introspection_rules
from stdimage.fields import StdImageField
rules = [
     (
         (StdImageField, ),
         [],
         {
             "size": ["size", {"default": None}],
             "thumbnail_size": ["thumbnail_size", {"default": None}],
         },
     ),
]
add_introspection_rules(rules, ["^stdimage\.fields",]) 
add_introspection_rules([], ['^jsonfield\.fields\.JSONField'])