using Microsoft.Xrm.Sdk;
using System;

namespace output
{
    /// <summary>
    /// Plugin development guide: https://docs.microsoft.com/powerapps/developer/common-data-service/plug-ins
    /// Best practices and guidance: https://docs.microsoft.com/powerapps/developer/common-data-service/best-practices/business-logic/
    /// </summary>
    public class ContactFullNameValidation : PluginBase
    {
        public ContactFullNameValidation(string unsecureConfiguration, string secureConfiguration)
            : base(typeof(ContactFullNameValidation))
        {
        }

        protected override void ExecuteDataversePlugin(ILocalPluginContext localPluginContext)
        {
            if (localPluginContext == null)
            {
                throw new ArgumentNullException(nameof(localPluginContext));
            }

            var context = localPluginContext.PluginExecutionContext;
            var tracingService = localPluginContext.TracingService;

            tracingService.Trace("ContactFullNameValidation plugin started.");

            if (context.InputParameters.Contains("Target") && context.InputParameters["Target"] is Entity)
            {
                var entity = (Entity)context.InputParameters["Target"];

                if (entity.LogicalName == "contact")
                {
                    tracingService.Trace("Processing contact entity.");

                    if (entity.Contains("fullname"))
                    {
                        var fullName = entity["fullname"].ToString();
                        tracingService.Trace($"Contact fullname: '{fullName}', Length: {fullName.Length}");

                        if (fullName.Length > 15)
                        {
                            tracingService.Trace("Fullname exceeds 15 characters. Throwing exception.");
                            throw new InvalidOperationException($"Contact fullname cannot exceed 15 characters. Current length: {fullName.Length}");
                        }
                    }
                }
            }

            tracingService.Trace("ContactFullNameValidation plugin completed successfully.");
        }
    }
}
