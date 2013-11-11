#-*- coding: utf-8 -*-
"""
Views for ads application

This module provides class-based views Create/Read/Update/Delete absractions
to work with Ad models.
"""
from django.conf import settings
from django.contrib import messages
from django.contrib.contenttypes.generic import generic_inlineformset_factory
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.contrib.sites.models import Site
from django.core.mail import send_mail
from django.core.urlresolvers import reverse
from django.http import QueryDict, Http404, HttpResponseRedirect
from django.shortcuts import render_to_response, redirect
from django.template import RequestContext
from django.utils.translation import ugettext as _
from django.utils.translation import ungettext
from django.utils.decorators import method_decorator
from django.views.generic import (ListView, DetailView, CreateView, UpdateView,
    DeleteView, TemplateView, FormView)

from geoads.models import Ad, AdSearch, AdPicture, AdSearchResult
from geoads.forms import (AdContactForm, AdPictureForm, AdSearchForm,
    AdSearchUpdateForm, AdSearchResultContactForm, BaseAdForm)
from geoads.utils import geocode
from geoads.signals import geoad_vendor_message, geoad_user_message


class LoginRequiredMixin(object):
    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super(LoginRequiredMixin, self).dispatch(request, *args, **kwargs)


class AdSearchView(ListView):
    """
    Class based ad search view

    GET method for searching: filtering, ordering, and browsing by page results
    POST method for saving a search
    """
    model = Ad
    search_id = None
    template_name = 'geoads/search.html'
    context_object_name = 'filter'
    no_results_msg = None  # Message when there is no results
    results_msg = None  # Message when number of results > 0
    ad_search_form = None
    ad_search = None
    #BUG: paginate_by = 14 doesn't work, I use django-paginator

    def dispatch(self, request, *args, **kwargs):
        # here, dispatch according to the request.method and url args/kwargs

        if 'search_id' in kwargs:
            self.search_id = kwargs['search_id']

        self.request = request
        self.args = args
        self.kwargs = kwargs

        if request.method == 'POST':
            if self.search_id:
                return self.update_search(request, *args, **kwargs)
            else:
                return self.create_search(request, *args, **kwargs)
        else:
            if self.search_id:
                return self.read_search(request, *args, **kwargs)
            elif request.GET != {}:
                return self.filter_ads(request, *args, **kwargs)
            else:
                return self.home(request, *args, **kwargs)

        #return super(AdSearchView, self).dispatch(request, *args, **kwargs)

    def home(self, request, *args, **kwargs):
        # request.method == 'GET' and request.GET only contains pages and sorting
        self._q = None
        self.object_list = self.get_queryset()
        context = self.get_context_data(object_list=self.object_list,
            initial_ads=True)
        return self.render_to_response(context)

    def filter_ads(self, request, *args, **kwargs):
        # request.method == 'GET' and request.GET != {} # after removing pages and potential sorting
        self._q = self.request.GET
        self.object_list = self.get_queryset()
        data = {'user': self.request.user,
            'search': self.request.GET.copy().urlencode()}
        self.ad_search_form = AdSearchForm(data)
        context = self.get_context_data(object_list=self.object_list,
            ad_search_form=True)
        self.get_msg()
        return self.render_to_response(context)

    def read_search(self, request, *args, **kwargs):
        # request.method == 'GET' and search_id is not None
        self.ad_search = AdSearch.objects.get(id=self.search_id)
        if self.ad_search.user != self.request.user:
                raise Http404
        self._q = QueryDict(self.ad_search.search)
        self.object_list = self.get_queryset()
        context = self.get_context_data(object_list=self.object_list)
        self.get_msg()
        return self.render_to_response(context)

    @method_decorator(login_required)
    def create_search(self, request, *args, **kwargs):
        # request.method == 'POST' and search_id is None
        # save the search
        #profile_detail_url = account_url(self.request)
        # return the results
        self.ad_search_form = AdSearchForm(request.POST)
        if self.ad_search_form.is_valid():
            self.ad_search_form.user = request.user
            self.ad_search = self.ad_search_form.save(commit=False)
            self.ad_search.content_type = ContentType.objects.get_for_model(self.model)
            self.ad_search.user = request.user
            self.ad_search.public = True
            self.ad_search.save()
            self.search_id = self.ad_search.id
            messages.add_message(self.request, messages.INFO,
                _(u'Votre recherche a bien été sauvegardée dans votre compte</a>.'), fail_silently=True)
                # when creation, we need to save related ads to ad_search_results
            #self.update_ad_search_results()
            return HttpResponseRedirect(reverse('search',
                kwargs={'search_id': self.search_id}))
        # this would be better no ?
        #self._q = QueryDict(self.ad_search.search)
        #self.object_list = self._get_queryset()
        #context = self.get_context_data(object_list=self.object_list)
        #return self.render_to_response(context)

    @method_decorator(login_required)
    def update_search(self, request, *args, **kwargs):
        # request.method == 'POST' and search_id is not None
        profile_detail_url = settings.LOGIN_REDIRECT_URL
        self.ad_search = AdSearch.objects.get(id=self.search_id)
        self.ad_search_form = AdSearchForm(request.POST, instance=self.ad_search)
        if self.ad_search_form.is_valid():
            self.ad_search_form.save()
            messages.add_message(self.request, messages.INFO,
                _(u'Votre recherche a bien été mise à jour ' +
                  u'dans <a href="%s">votre compte</a>.')
                % (profile_detail_url), fail_silently=True)
        # need to be sure that self.ad_search.search is well updated
        self._q = QueryDict(self.ad_search.search)
        self.object_list = self.get_queryset()
        context = self.get_context_data(object_list=self.object_list)
        self.get_msg()
        return self.render_to_response(context)

    def get_queryset(self):
        filter = self.model.filterset()(self._q)
        return filter

    def get_context_data(self, initial_ads=None, ad_search_form=None, **kwargs):
        context = super(AdSearchView, self).get_context_data(**kwargs)
        if initial_ads == True:
            context['initial_ads'] = self.model.objects.select_related()\
                .order_by('-create_date')[0:10]
        if ad_search_form == True:
            context['ad_search_form'] = self.ad_search_form  # need to be filled with current search
        context['search_id'] = self.search_id  # what to do with that
        return context

    def get_msg(self):
        """
        Search result default message
        """
        if len(self.object_list.qs) == 0:
            messages.add_message(self.request, messages.INFO,
                self.get_no_results_msg(), fail_silently=True)
        else:
            messages.add_message(self.request, messages.INFO,
                self.get_results_msg(), fail_silently=True)

    def get_no_results_msg(self):
        """
        Message for search that give 0 results
        """
        if self.no_results_msg is None:
            return _(u'Aucune annonce ne correspond à votre recherche. ' +\
                     u'Elargissez votre zone de recherche ou modifiez les critères.')
        return self.no_results_msg

    def get_results_msg(self):
        """
        Message for search that give 1 or more results
        """
        #TODO: should have information if search come from a saved search
        if self.results_msg is None:
            msg = ungettext(u'%s annonce correspondant à votre recherche. ',
                    u'%s annonces correspondant à votre recherche. ',
                    len(self.object_list.qs)) \
                            % (len(self.object_list.qs))
            return msg
        return self.results_msg


class AdSearchUpdateView(LoginRequiredMixin, UpdateView):
    """
    Class based update search view
    Render public or not
    Attach message
    """
    model = AdSearch
    form_class = AdSearchUpdateForm
    template_name = "geoads/adsearch_update.html"
    success_url = settings.LOGIN_REDIRECT_URL


class AdSearchDeleteView(DeleteView): #LoginRequiredMixin, 
    """
    Class based delete search ad
    """
    model = AdSearch
    template_name = "geoads/adsearch_confirm_delete.html"
    success_url = settings.LOGIN_REDIRECT_URL


    def get_object(self, queryset=None):
        """ Ensure object is owned by request.user. """
        obj = super(AdSearchDeleteView, self).get_object()
        if not obj.user == self.request.user:
            raise Http404
        return obj

    #def get_success_url(self):
    #    """ Redirect to user account page """
    #    messages.add_message(self.request, messages.INFO,
    #        _(u'Votre recherche a bien été supprimée.'), fail_silently=True)
    #    #return account_url(self.request)
    #    return HttpResponseRedirect(reverse('search'))


class AdDetailView(DetailView):
    """
    Class based detail ad
    """
    model = Ad  # changed in urls
    context_object_name = 'ad'
    template_name = 'geoads/view.html'
    contact_form = AdContactForm

    def get_context_data(self, **kwargs):
        context = super(AdDetailView, self).get_context_data(**kwargs)
        context['contact_form'] = self.contact_form()
        context['sent_mail'] = False
        return context

    @method_decorator(login_required)
    def post(self, request, *args, **kwargs):
        """ used for contact message between users """
        contact_form = self.contact_form(request.POST)
        sent_mail = False
        if contact_form.is_valid():
            instance = contact_form.save(commit=False)
            instance.content_object = self.get_object()
            instance.user = request.user
            instance.save()
            geoad_user_message.send(sender=Ad, ad=self.get_object(), user=instance.user, message=instance.message)
            sent_mail = True
            messages.add_message(request, messages.INFO,
                _(u'Votre message a bien été envoyé.'), fail_silently=True)
        return render_to_response(self.template_name, {'ad': self.get_object(),
                                  'contact_form': contact_form,
                                  'sent_mail': sent_mail},
                                  context_instance=RequestContext(request))

    def get_queryset(self):
        return self.model.objects.all()


class AdCreateView(LoginRequiredMixin, CreateView):
    """
    Class based create ad
    """
    model = Ad  # overriden in specific project urls
    template_name = 'geoads/edit.html'
    ad_picture_form = AdPictureForm

    def form_valid(self, form):
        context = self.get_context_data()
        picture_formset = context['picture_formset']
        if picture_formset.is_valid():
            self.object = form.save(commit=False)
            self.object.user = self.request.user
            user_entered_address = form.cleaned_data['user_entered_address']
            if settings.BYPASS_GEOCODE is True:
                self.object.address = u"[{u'geometry': {u'location': {u'lat': 48.868356, u'lng': 2.330378}, u'viewport': {u'northeast': {u'lat': 48.8697049802915, u'lng': 2.331726980291502}, u'southwest': {u'lat': 48.8670070197085, u'lng': 2.329029019708498}}, u'location_type': u'ROOFTOP'}, u'address_components': [{u'long_name': u'1', u'types': [u'street_number'], u'short_name': u'1'}, {u'long_name': u'Rue de la Paix', u'types': [u'route'], u'short_name': u'Rue de la Paix'}, {u'long_name': u'2nd arrondissement of Paris', u'types': [u'sublocality', u'political'], u'short_name': u'2nd arrondissement of Paris'}, {u'long_name': u'Paris', u'types': [u'locality', u'political'], u'short_name': u'Paris'}, {u'long_name': u'Paris', u'types': [u'administrative_area_level_2', u'political'], u'short_name': u'75'}, {u'long_name': u'\xcele-de-France', u'types': [u'administrative_area_level_1', u'political'], u'short_name': u'IdF'}, {u'long_name': u'France', u'types': [u'country', u'political'], u'short_name': u'FR'}, {u'long_name': u'75002', u'types': [u'postal_code'], u'short_name': u'75002'}], u'formatted_address': u'1 Rue de la Paix, 75002 Paris, France', u'types': [u'street_address']}]"
                self.object.location = 'POINT (2.3303780000000001 48.8683559999999986)'
            else:
                geo_info = geocode(user_entered_address.encode('ascii', 'ignore'))
                self.object.address = geo_info['address']
                self.object.location = geo_info['location']
            self.object.save()
            picture_formset.instance = self.object
            picture_formset.save()
            return redirect('complete', permanent=True)

    def form_invalid(self, form):
        send_mail(_(u"[%s] %s invalid form while creating an ad") %
                  (Site.objects.get_current().name, self.request.user.email),
                  "%s" % (form.errors), 'contact@achetersanscom.com',
                  ["contact@achetersanscom.com"], fail_silently=True)
        return self.render_to_response(self.get_context_data(form=form))

    def get_context_data(self, **kwargs):
        context = super(AdCreateView, self).get_context_data(**kwargs)
        if self.request.POST:
            PictureFormset = generic_inlineformset_factory(AdPicture, form=self.ad_picture_form,
                                                           extra=4, max_num=4)
            context['picture_formset'] = PictureFormset(self.request.POST,
                                                        self.request.FILES)
        else:
            PictureFormset = generic_inlineformset_factory(AdPicture, form=self.ad_picture_form,
                                                           extra=4, max_num=4)
            context['picture_formset'] = PictureFormset()
        return context


class AdUpdateView(LoginRequiredMixin, UpdateView):
    """
    Class base update ad
    """
    model = Ad  # overriden in specific project urls
    template_name = 'geoads/edit.html'
    ad_picture_form = AdPictureForm
    form_class = BaseAdForm

    def form_valid(self, form):
        context = self.get_context_data()
        picture_formset = context['picture_formset']
        if picture_formset.is_valid():
            self.object = form.save(commit=False)
            user_entered_address = form.cleaned_data['user_entered_address']
            if settings.BYPASS_GEOCODE == True:
                self.object.address = u"[{u'geometry': {u'location': {u'lat': 48.868356, u'lng': 2.330378}, u'viewport': {u'northeast': {u'lat': 48.8697049802915, u'lng': 2.331726980291502}, u'southwest': {u'lat': 48.8670070197085, u'lng': 2.329029019708498}}, u'location_type': u'ROOFTOP'}, u'address_components': [{u'long_name': u'1', u'types': [u'street_number'], u'short_name': u'1'}, {u'long_name': u'Rue de la Paix', u'types': [u'route'], u'short_name': u'Rue de la Paix'}, {u'long_name': u'2nd arrondissement of Paris', u'types': [u'sublocality', u'political'], u'short_name': u'2nd arrondissement of Paris'}, {u'long_name': u'Paris', u'types': [u'locality', u'political'], u'short_name': u'Paris'}, {u'long_name': u'Paris', u'types': [u'administrative_area_level_2', u'political'], u'short_name': u'75'}, {u'long_name': u'\xcele-de-France', u'types': [u'administrative_area_level_1', u'political'], u'short_name': u'IdF'}, {u'long_name': u'France', u'types': [u'country', u'political'], u'short_name': u'FR'}, {u'long_name': u'75002', u'types': [u'postal_code'], u'short_name': u'75002'}], u'formatted_address': u'1 Rue de la Paix, 75002 Paris, France', u'types': [u'street_address']}]"
                self.object.location = 'POINT (2.3303780000000001 48.8683559999999986)'
            else:
                address = user_entered_address.encode('ascii', 'ignore')
                geo_info = geocode(user_entered_address.encode('ascii', 'ignore'))
                self.object.address = geo_info['address']
                self.object.location = geo_info['location']
            self.object.save()
            picture_formset.instance = self.object
            picture_formset.save()
            return redirect('complete', permanent=True)


    def get_object(self, queryset=None):
        """ Hook to ensure object is owned by request.user. """
        obj = self.model.objects.get(id=self.kwargs['pk'])
        if not obj.user == self.request.user:
            raise Http404

        return obj

    def get_context_data(self, **kwargs):
        context = super(AdUpdateView, self).get_context_data(**kwargs)
        if self.request.POST:
            PictureFormset = generic_inlineformset_factory(AdPicture, form=self.ad_picture_form,
                                                   extra=4, max_num=4)
            context['picture_formset'] = PictureFormset(self.request.POST,
                                                  self.request.FILES,
                                                  instance=context['object'])
        else:
            PictureFormset = generic_inlineformset_factory(AdPicture, form=self.ad_picture_form,
                                                   extra=4, max_num=4)
            context['picture_formset'] = PictureFormset(instance=context['object'])
        return context


class CompleteView(LoginRequiredMixin, TemplateView):
    template_name = "geoads/validation.html"


class AdDeleteView(LoginRequiredMixin, DeleteView):
    """
    Class based delete ad
    """
    model = Ad  # "normally" overrided in specific project urls
    template_name = "geoads/ad_confirm_delete.html"

    def get_object(self, queryset=None):
        """ Ensure object is owned by request.user. """
        obj = super(AdDeleteView, self).get_object()
        if not obj.user == self.request.user:
            raise Http404
        return obj

    def get_success_url(self):
        """ Redirect to user account page"""
        messages.add_message(self.request, messages.INFO, _(u'Votre annonce a bien été supprimée.'), fail_silently=True)
        return settings.LOGIN_REDIRECT_URL


class AdPotentialBuyersView(LoginRequiredMixin, ListView):
    """
    Class based view for listing potential buyers of an ad
    """
    model = Ad
    search_model = AdSearchResult
    template_name = "geoads/adpotentialbuyers_list.html"
    pk = None

    def get_queryset(self):
        # should return a list of buyers, in fact AdSearch instances
        self.pk = self.kwargs['pk']
        content_type = ContentType.objects.get_for_model(self.model)

        # Below an implementation that could be used to return form
        # AdSearchResultFormSet = modelformset_factory(AdSearchResult, form=AdSearchResultContactForm)
        # formset = AdSearchResultFormSet(queryset=AdSearchResult.objects.filter(object_pk=self.pk).filter(content_type=content_type))
        # return formset

        queryset = self.search_model.objects.filter(object_pk=self.pk)\
            .filter(content_type=content_type).filter(ad_search__public=True)
        queryset.contacted = queryset.filter(contacted=True)
        queryset.not_contacted = queryset.exclude(contacted=True)
        for obj in queryset.not_contacted:
            obj.form = AdSearchResultContactForm(instance=obj)
            obj.form_action = reverse('contact_buyer', kwargs={'adsearchresult_id': obj.id})
        return queryset

    def get_context_data(self, **kwargs):
        """extra context"""
        context = super(AdPotentialBuyersView, self).get_context_data(**kwargs)
        context['object'] = self.model.objects.get(id=self.pk)
        return context


class AdPotentialBuyerContactView(LoginRequiredMixin, FormView):
    """
    Potential buyer contact view for an Ad
    """
    model_class = AdSearchResult
    form_class = AdSearchResultContactForm
    template_name = ""  # unused

    def form_valid(self, form):
        self.message = form.cleaned_data['message']
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        ad_search_result_id = self.kwargs['adsearchresult_id']
        # Below, tricky 'hack', depend on the context, 
        # ad_search_result_id is AdSearchResult instance or just an id ! 
        # Don't know why.
        if isinstance(ad_search_result_id, self.model_class):
            ad_search_result = ad_search_result_id
        else:
            ad_search_result = self.model_class.objects.get(id=ad_search_result_id)
        ad_search_result.contacted = True
        ad_search_result.save()
        geoad_vendor_message.send(sender=Ad, ad=ad_search_result.content_object, ad_search=ad_search_result.ad_search,
                                  user=ad_search_result.ad_search.user, message=self.message)
        return reverse('contact_buyers', kwargs={'pk': ad_search_result.object_pk})
