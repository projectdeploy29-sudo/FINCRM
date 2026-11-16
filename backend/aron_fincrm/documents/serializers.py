from rest_framework import serializers
from documents.models import DocumentCategory, Document, DocumentAccessLog
from organizations.tenant import get_user_organization

class DocumentCategorySerializer(serializers.ModelSerializer):
 class Meta: model=DocumentCategory; fields='__all__'; read_only_fields=('organization',)
 def create(self,data):
  req=self.context['request']; return super().create({**data,'organization':get_user_organization(req.user,req)})
class DocumentSerializer(serializers.ModelSerializer):
 file_available=serializers.SerializerMethodField()
 class Meta:
  model=Document; fields='__all__'; read_only_fields=('organization','file_name','file_type','uploaded_at','archived_at','current_version','status'); extra_kwargs={'file':{'write_only':True}}
 def get_file_available(self,obj): return bool(obj.file)
 def validate_file(self,value):
  if value.size>15*1024*1024: raise serializers.ValidationError('Maximum file size is 15 MB.')
  if value.content_type not in {'application/pdf','image/jpeg','image/png'}: raise serializers.ValidationError('Only PDF, JPEG and PNG files are accepted.')
  return value
 def validate(self,attrs):
  req=self.context['request']; org=get_user_organization(req.user,req)
  instance=self.instance
  category=attrs.get('category',getattr(instance,'category',None)); app=attrs.get('application',getattr(instance,'application',None)); customer=attrs.get('customer',getattr(instance,'customer',None))
  if not org or (app and app.organization_id!=org.id) or (customer and customer.organization_id!=org.id) or (category and category.organization_id!=org.id): raise serializers.ValidationError('Document references must belong to your organization.')
  if app and customer and app.customer_id!=customer.id: raise serializers.ValidationError('Document customer must match its application customer.')
  if not instance and attrs.get('status',Document.Status.UPLOADED)!=Document.Status.UPLOADED: raise serializers.ValidationError({'status':'New documents must start in Uploaded status.'})
  return attrs
 def create(self,data):
  req=self.context['request']; f=data['file']; org=get_user_organization(req.user,req)
  return super().create({**data,'organization':org,'file_name':f.name,'file_type':f.content_type,'file_size':f.size})
 def update(self,instance,data):
  file=data.get('file')
  if file:
   data.update(file_name=file.name,file_type=file.content_type,file_size=file.size,current_version=instance.current_version+1)
  return super().update(instance,data)
